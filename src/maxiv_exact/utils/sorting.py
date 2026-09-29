def parse_entry_number(hdf5_path):
    """
    If hdf5_path starts with 'entry####', return the integer ####, else -1.
    """
    if not hdf5_path:
        return -1
    parts = hdf5_path.split("/")
    if parts and parts[0].startswith("entry"):
        digits = ''.join(ch for ch in parts[0] if ch.isdigit())
        if digits.isdigit():
            return int(digits)
    return -1

# --- Custom widget for each plotted curve in the Plotted Data tab ---
