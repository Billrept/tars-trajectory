import math
from datetime import datetime,timezone
from astropy.time import Time
from astropy.utils import iers
iers.conf.auto_download=False

def jd_to_datetime(jd: float) -> datetime:
    """Convert Julian Date to Python datetime (UTC)."""
    if not math.isfinite(jd):
        raise ValueError('Julian date must be finite')
    return Time(jd, format='jd', scale='tdb').utc.to_datetime(timezone=timezone.utc)

def datetime_to_jd(dt: datetime) -> float:
    """Convert Python datetime (UTC) to Julian Date."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return float(Time(dt.astimezone(timezone.utc), scale='utc').tdb.jd)

def iso_to_jd(iso_str: str) -> float:
    """Convert ISO date string to Julian Date."""
    dt = datetime.fromisoformat(iso_str)
    return datetime_to_jd(dt)

def jd_to_iso(jd: float) -> str:
    """Convert Julian Date to ISO date string."""
    return jd_to_datetime(jd).isoformat()

def jds_to_iso(epochs):
    """Convert an array of TDB epochs in one vectorized operation."""
    dates=Time(epochs,format='jd',scale='tdb').utc
    dates.precision=6
    return [str(value)+'Z' for value in dates.isot]
