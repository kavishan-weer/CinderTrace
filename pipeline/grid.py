"""Shared H3 grid contract. IDs are strings for safe browser interchange."""
import h3

H3_RESOLUTION = 6

def cell_metadata(cell):
    lat, lon = h3.cell_to_latlng(cell)
    return {"h3_cell": cell, "lat": lat, "lon": lon,
            "area_km2": h3.cell_area(cell, unit="km^2")}
