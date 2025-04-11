"""DB tables."""

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
)
from sqlalchemy.ext.declarative import declarative_base

declarative_Base = declarative_base()


class Target(declarative_Base):
    """Store target info."""

    __tablename__ = "target"
    id = Column(Integer, primary_key=True)

    name = Column(String(50))
    pmra = Column(Float)
    pmdec = Column(Float)
    parallax = Column(Float)

    @property
    def params(self) -> dict[str, float]:
        """Get star properties."""
        return {"pmra": self.pmra, "pmdec": self.pmdec, "parallax": self.parallax}


class GDAS_profile(declarative_Base):
    """GDAS profiles for Telfit."""

    __tablename__ = "GDAS"
    id = Column(Integer, primary_key=True)

    gdas_filename = Column(String(60), unique=True)
    instrument = Column(String(50))
    download_date = Column(DateTime)

    def __repr__(self) -> str:  # noqa: D105
        return f"Target({self.name=}"

    def __str__(self) -> str:  # noqa: D105
        string = f"GDAS profile from {self.instrument}"
        return string
