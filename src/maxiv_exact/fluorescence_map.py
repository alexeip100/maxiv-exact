"""Qt-free XRF map loading and Gaussian peak analysis.

No smoothing along the incident-energy dimension and no SA correction physics.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
import numpy as np
import h5py
from scipy.optimize import least_squares


@dataclass
class FLMap:
    counts: np.ndarray  # [incident, detector channel]
    incident: np.ndarray
    detector: np.ndarray
    incident_label: str
    source: str


def integrate_fluorescence_roi(map_counts, center, half_width):
    """Inclusive detector-channel ROI sum, one value per incident scan."""
    values=np.asarray(map_counts)
    if values.ndim != 2:
        raise ValueError('Fluorescence map must be two-dimensional.')
    if not 0 <= int(center) < values.shape[1] or int(half_width) < 0:
        raise ValueError('ROI center or half-width is invalid.')
    lo=max(0,int(center)-int(half_width))
    hi=min(values.shape[1],int(center)+int(half_width)+1)
    roi=values[:,lo:hi]
    result=np.nansum(roi,axis=1,dtype=float)
    result[~np.any(np.isfinite(roi),axis=1)]=np.nan
    return result


def load_fluorescence_map(path: str) -> FLMap:
    """Read Xspress3 Nexus or an unambiguous 2D HDF5 count dataset."""
    with h5py.File(path, 'r') as h:
        preferred = ['entry/instrument/xspress3/data', 'entry/data/data']
        ds = next((h[p] for p in preferred if p in h and isinstance(h[p], h5py.Dataset)), None)
        if ds is None:
            matches = []
            def visit(name, obj):
                if isinstance(obj, h5py.Dataset) and obj.ndim in (2, 3) and obj.shape[-1] >= 128 and obj.shape[0] > 1:
                    matches.append((name, obj))
            h.visititems(visit)
            if len(matches) != 1:
                raise ValueError('No unique fluorescence map found. Expected entry/instrument/xspress3/data; '
                                 f'found {len(matches)} candidate arrays.')
            ds = matches[0][1]
        if ds.ndim == 3 and ds.shape[1] == 1:
            counts = np.asarray(ds[:, 0, :], dtype=float)
        elif ds.ndim == 2:
            counts = np.asarray(ds[:], dtype=float)
        else:
            raise ValueError(f'Unsupported detector shape {ds.shape}; only a single detector supported.')
        n = counts.shape[0]
        energy = None
        for key in ['entry/instrument/monochromator/energy', 'entry/instrument/mono/energy',
                    'entry/data/energy', 'entry/energy', 'entry/sample/energy']:
            if key in h and isinstance(h[key], h5py.Dataset):
                trial = np.asarray(h[key][...], dtype=float).ravel()
                if trial.size == n and np.isfinite(trial).all() and np.ptp(trial) > 0:
                    energy = trial
                    break
    return FLMap(counts, np.arange(n, dtype=float) if energy is None else energy,
                 np.arange(counts.shape[1], dtype=float),
                 'Incident scan index' if energy is None else 'Incident energy (eV)', str(path))


def gaussian_area(x, area, center, fwhm):
    sigma = max(float(fwhm), 1e-9) / (2 * np.sqrt(2 * np.log(2)))
    return float(area) / (sigma * np.sqrt(2*np.pi)) * np.exp(-.5 * ((np.asarray(x)-center)/sigma)**2)


def evaluate_model(x, peaks, bg0=0., bg1=0.):
    x = np.asarray(x, dtype=float)
    y = np.full_like(x, float(bg0)) + float(bg1) * (x - np.mean(x))
    components = []
    for p in peaks:
        c = gaussian_area(x, p['area'], p['center'], p['fwhm'])
        components.append(c)
        y += c
    return y, components


def fit_detector_spectrum(x, counts, peaks, bg0=0., bg1=0., *, linear_background=True,
                          width_soft_limits=(80., 160.), width_softness=40.):
    """Fit independent areas with optional free centers/widths; Poisson-deviance residual.

    peak dicts: name, area, center, fwhm, free_center, free_width.
    Returns fitted peak list and background along with model and residuals.
    """
    x = np.asarray(x, float).ravel()
    y = np.asarray(counts, float).ravel()
    if x.size != y.size or x.size < 8 or not np.isfinite(y).all() or np.any(y < 0):
        raise ValueError('Fit needs equally sized finite detector axes and nonnegative counts.')
    low_soft, high_soft = map(float, width_soft_limits)
    width_softness = float(width_softness)
    if not (np.isfinite([low_soft, high_soft, width_softness]).all()
            and 0 < low_soft < high_soft and width_softness > 0):
        raise ValueError("Width soft limits must be positive, ordered and finite; softness must be positive.")
    specs = [dict(p) for p in peaks]
    if not specs:
        raise ValueError('Add at least one peak before fitting.')
    span = float(np.ptp(x))
    x0 = [max(float(bg0), 0.)]
    bounds_lo = [0.]
    bounds_hi = [np.inf]
    if linear_background:
        x0.append(float(bg1)); bounds_lo.append(-np.inf); bounds_hi.append(np.inf)
    for p in specs:
        x0.append(max(float(p['area']), 0.)); bounds_lo.append(0.); bounds_hi.append(np.inf)
        if p.get('free_center', True):
            x0.append(float(p['center'])); bounds_lo.append(float(x.min())); bounds_hi.append(float(x.max()))
        if p.get('free_width', True):
            x0.append(max(float(p['fwhm']), .1)); bounds_lo.append(.1); bounds_hi.append(max(2*span, .2))
    def unpack(v):
        k=0; b0=float(v[k]);k+=1
        b1=float(v[k]) if linear_background else 0.
        if linear_background:k+=1
        out=[]
        for p in specs:
            q=dict(p);q['area']=float(v[k]);k+=1
            if q.get('free_center', True):q['center']=float(v[k]);k+=1
            if q.get('free_width', True):q['fwhm']=float(v[k]);k+=1
            out.append(q)
        return out,b0,b1
    def residual(v):
        pp, b0,b1=unpack(v)
        model,_=evaluate_model(x,pp,b0,b1)
        # Poisson deviance, with stable handling of empty bins.
        model=np.clip(model,1e-8,None)
        dev=2*(model-y+np.where(y>0,y*np.log(np.maximum(y,1e-12)/model),0.))
        data_residual = np.sign(y-model)*np.sqrt(np.maximum(dev,0.))
        # Flat-bottom quadratic penalty: no restraint within the preferred
        # FWHM interval, gentle rubber-band pull outside. The input x and
        # Gaussian widths are in physical detector energy (eV).
        penalties = [min(0., p["fwhm"]-low_soft, high_soft-p["fwhm"]) / width_softness
                     for p in pp if p.get("free_width", True)]
        return np.r_[data_residual, penalties]
    result=least_squares(residual,np.array(x0,float),bounds=(bounds_lo,bounds_hi),max_nfev=1200)
    pp,b0,b1=unpack(result.x)
    model,components=evaluate_model(x,pp,b0,b1)
    return {'peaks':pp,'bg0':b0,'bg1':b1,'model':model,'components':components,
            'residual':y-model,'success':bool(result.success), 'message':result.message,
            'deviance':float(np.dot(result.fun[:len(y)],result.fun[:len(y)])),
            'width_penalty':float(np.dot(result.fun[len(y):],result.fun[len(y):]))}


def save_fit_configuration(path, peaks, bg0, bg1):
    obj={'format':'exact-fl-peak-config-v1','peaks':peaks,'bg0':float(bg0),'bg1':float(bg1)}
    Path(path).write_text(json.dumps(obj,indent=2),encoding='utf8')


def load_fit_configuration(path):
    obj=json.loads(Path(path).read_text(encoding='utf8'))
    if obj.get('format')!='exact-fl-peak-config-v1' or not isinstance(obj.get('peaks'),list):
        raise ValueError('Not an EXACT fluorescence peak configuration.')
    return obj


def fit_polynomial_trend(x, values, degree, success=None):
    """Robust degree 0/1/2 polynomial for a Pass-1 fitted parameter trend.

    The input scan coordinate is normalized before polynomial fitting.
    A least-squares / MAD rejection loop prevents failed fits and large
    outliers from dominating the shared parameter trend.
    """
    x=np.asarray(x,float); y=np.asarray(values,float)
    valid=np.isfinite(x)&np.isfinite(y)
    if success is not None:valid &= np.asarray(success,bool)
    if valid.sum()<int(degree)+2:raise ValueError('Not enough reliable fit points for polynomial trend.')
    xx=(x-np.mean(x))/(max(np.ptp(x),1e-12)/2.)
    keep=valid.copy()
    for _ in range(5):
        coeff=np.polynomial.polynomial.polyfit(xx[keep],y[keep],int(degree))
        resid=y-np.polynomial.polynomial.polyval(xx,coeff)
        med=np.median(resid[keep]);mad=1.4826*np.median(abs(resid[keep]-med))
        if mad<1e-12:break
        candidate=valid & (abs(resid-med)<=4.0*mad)
        if candidate.sum()<int(degree)+2 or np.array_equal(candidate,keep):break
        keep=candidate
    curve=np.polynomial.polynomial.polyval(xx,coeff)
    return curve,keep


def batch_row_for_incident(starts, incident_index):
    """Find the fitted batch bin containing the selected original scan row."""
    starts=np.asarray(starts,dtype=int)
    if starts.ndim != 1 or len(starts)==0 or np.any(np.diff(starts)<=0):
        raise ValueError('Batch start indices must be a nonempty increasing sequence.')
    return int(np.clip(np.searchsorted(starts,int(incident_index),side='right')-1,
                       0,len(starts)-1))


def fit_fluorescence_batch(counts, detector_energy, peaks, *, bin_size=1,
                           fit_slice=None, bg0=0., bg1=0., linear_background=True,
                           refine_shapes=False, center_tolerance=8., width_fraction=.15,
                           trend_constraints=None, prior_result=None, progress=None, cancelled=None,
                           width_soft_limits=(80.,160.), width_softness=40.):
    """Independent Pass 1 then optional trend-constrained Pass 2.

    Pass 1 honours free_center/free_width for every peak. Pass 2 uses
    user-selected polynomial trends, evaluated at the binned scan index,
    to FIX the selected shapes while freely refitting peak areas and BG.
    Areas are never smoothed along incident energy.
    """
    from scipy.optimize import lsq_linear
    data=np.asarray(counts,float); x=np.asarray(detector_energy,float)
    if data.ndim!=2 or data.shape[1]!=x.size or not np.isfinite(data).all() or np.any(data<0):
        raise ValueError('Batch needs finite nonnegative [scan, channel] counts.')
    if not peaks:raise ValueError('Add a peak before starting batch fitting.')
    bin_size=int(bin_size)
    if bin_size<1:raise ValueError('Binning factor must be positive.')
    a,b=(0,len(x)) if fit_slice is None else tuple(map(int,fit_slice))
    if a<0 or b>len(x) or b-a<16:raise ValueError('Invalid detector fitting range.')
    starts=np.arange(0,len(data),bin_size)
    sums=np.add.reduceat(data,starts,axis=0)[:,a:b]
    effective_n=np.minimum(bin_size,len(data)-starts)
    n=len(starts);m=len(peaks);xx=x[a:b]
    orig=[dict(p) for p in peaks]
    def empty():
        return dict(areas=np.full((n,m),np.nan),area_stderr=np.full((n,m),np.nan),
                    centers=np.full((n,m),np.nan),widths=np.full((n,m),np.nan),
                    background=np.full((n,2),np.nan),deviance=np.full(n,np.nan),
                    success=np.zeros(n,dtype=bool))
    base=empty()
    if prior_result is not None:
        if not np.array_equal(prior_result['starts'],starts) or prior_result['fit_slice']!=(a,b):
            raise ValueError('Pass 2 configuration differs from the stored Pass 1 result.')
        base={k:np.array(prior_result['pass1'][k],copy=True) for k in base}
    def linear_fit(y, pp):
        cols=[gaussian_area(xx,1.,p['center'],p['fwhm']) for p in pp]
        cols += [np.ones(len(xx))]
        if linear_background:cols += [xx-xx.mean()]
        A=np.column_stack(cols)
        lo=np.r_[np.zeros(m+1), [-np.inf] if linear_background else []]
        hi=np.full(A.shape[1],np.inf)
        weights=1/np.sqrt(np.maximum(y,1.))
        for _ in range(3):
            Aw=A*weights[:,None];yw=y*weights
            candidate=np.linalg.lstsq(Aw,yw,rcond=None)[0]
            if np.all(candidate[:m+1]>=0):co=candidate
            else:co=lsq_linear(Aw,yw,bounds=(lo,hi),max_iter=120).x
            pred=np.maximum(A@co,1e-8)
            weights=1/np.sqrt(np.maximum(pred,1.))
        bg=np.array([co[m],co[m+1] if linear_background else 0.])
        covariance=np.linalg.pinv(A.T@(A/np.maximum(pred,1.)[:,None]),rcond=1e-10)
        stderr=np.sqrt(np.maximum(np.diag(covariance)[:m],0.))
        dev=2*(pred-y+np.where(y>0,y*np.log(np.maximum(y,1e-12)/pred),0.))
        return co[:m],stderr,bg,float(np.maximum(dev,0.).sum())
    def record(store,i,pp,areas,stderr,bg,dev):
        store['areas'][i]=areas;store['area_stderr'][i]=stderr
        store['centers'][i]=[p['center'] for p in pp]
        store['widths'][i]=[p['fwhm'] for p in pp]
        store['background'][i]=bg;store['deviance'][i]=dev;store['success'][i]=True
    if prior_result is None:
        for i,y in enumerate(sums):
            if cancelled and cancelled():raise RuntimeError("Batch fit aborted")
            try:
                if any(p.get('free_center',False) or p.get('free_width',False) for p in orig):
                    seeded=[dict(p,area=max(float(p['area']),1.)) for p in orig]
                    r=fit_detector_spectrum(xx,y,seeded,bg0*effective_n[i],bg1*effective_n[i],linear_background=linear_background,
                                            width_soft_limits=width_soft_limits, width_softness=width_softness)
                    pp=r['peaks']
                else:pp=orig
                area,err,bg,dev=linear_fit(y,pp)
                record(base,i,pp,area,err,bg,dev)
            except (ValueError,ArithmeticError,RuntimeError,np.linalg.LinAlgError,OverflowError):pass
            if progress and (i%max(1,n//100)==0 or i==n-1):progress(i+1,n)
    if not refine_shapes:
        return dict(**base,starts=starts,bin_size=bin_size,bin_counts=effective_n,peaks=orig,
                    fit_slice=(a,b),refined=False,linear_background=bool(linear_background),
                    pass1=base,trend_curves={},trend_constraints={},
                    center_tolerance=float(center_tolerance),width_fraction=float(width_fraction))
    cfg=trend_constraints or {}
    scanx=np.array([float(np.mean(np.arange(start,start+count))) for start,count in zip(starts,effective_n)])
    curves={};kept={}
    for (j,parameter),degree in cfg.items():
        j=int(j)
        if not 0<=j<m or parameter not in ('center','width') or degree not in (0,1,2):
            raise ValueError('Invalid trend selection.')
        key='centers' if parameter=='center' else 'widths'
        curve,mask=fit_polynomial_trend(scanx,base[key][:,j],degree,base['success'])
        curves[(j,parameter)]=curve;kept[(j,parameter)]=mask
    out=empty()
    for i,y in enumerate(sums):
        if cancelled and cancelled():raise RuntimeError("Batch fit aborted")
        if not base['success'][i]:continue
        try:
            pp=[]
            for j,p in enumerate(orig):
                q=dict(p,center=float(base['centers'][i,j]),fwhm=float(base['widths'][i,j]))
                if (j,'center') in curves:q['center']=float(curves[(j,'center')][i])
                if (j,'width') in curves:q['fwhm']=max(.1,float(curves[(j,'width')][i]))
                pp.append(q)
            area,err,bg,dev=linear_fit(y,pp)
            record(out,i,pp,area,err,bg,dev)
        except (ValueError,ArithmeticError,RuntimeError,np.linalg.LinAlgError,OverflowError):pass
        if progress and (i%max(1,n//100)==0 or i==n-1):progress(i+1,n)
    return dict(**out,starts=starts,bin_size=bin_size,bin_counts=effective_n,peaks=orig,
                fit_slice=(a,b),refined=True,linear_background=bool(linear_background),
                pass1=base,trend_curves=curves,trend_constraints=cfg,trend_inliers=kept,
                center_tolerance=float(center_tolerance),width_fraction=float(width_fraction))


def extract_fitted_fy(batch, incident_energy):
    """Return fit areas and 1-sigma linear-fit errors per original incident scan.

    Batch fitting uses summed counts per bin. This conversion divides by the
    *actual* bin count, including the possibly shorter last bin; it does not
    normalize by incident flux (I0) and does not invert signals for IPFY.
    """
    axis = np.asarray(incident_energy, dtype=float)
    starts = np.asarray(batch['starts'], dtype=int)
    counts = np.asarray(batch['bin_counts'], dtype=int)
    areas = np.asarray(batch['areas'], dtype=float)
    errors = np.asarray(batch['area_stderr'], dtype=float)
    success = np.asarray(batch['success'], dtype=bool)
    if (axis.ndim != 1 or starts.ndim != 1 or counts.shape != starts.shape
            or areas.shape != errors.shape or areas.shape[0] != len(starts)
            or success.shape != starts.shape or not len(starts)
            or np.any(counts <= 0) or np.any(starts < 0)
            or np.any(starts + counts > len(axis))):
        raise ValueError('Inconsistent fluorescence batch export dimensions.')
    midpoints = np.array([float(np.mean(axis[s:s+n])) for s,n in zip(starts,counts)])
    normalized_areas = areas / counts[:, None]
    normalized_errors = errors / counts[:, None]
    normalized_areas[~success, :] = np.nan
    normalized_errors[~success, :] = np.nan
    return midpoints, normalized_areas, normalized_errors


def reconstruct_component(batch, detector_energy, peak_index):
    """Reconstruct one fluorescence Gaussian, retaining bin-summed count units."""
    x = np.asarray(detector_energy, dtype=float)
    if x.ndim != 1 or peak_index < 0 or peak_index >= len(batch['peaks']):
        raise ValueError('Invalid detector axis or fitted fluorescence component.')
    a, b = batch['fit_slice']
    if not (0 <= a < b <= len(x)):
        raise ValueError('Invalid detector fit interval.')
    out = np.full((len(batch['success']), len(x)), np.nan, dtype=float)
    for i, good in enumerate(batch['success']):
        if good:
            out[i, a:b] = gaussian_area(x[a:b], batch['areas'][i,peak_index],
                                         batch['centers'][i,peak_index], batch['widths'][i,peak_index])
    return out
