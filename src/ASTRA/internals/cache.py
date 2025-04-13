"""Database connection to store target info."""

import datetime
from pathlib import Path

import numpy as np
from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy_utils import create_database, database_exists

from ASTRA.internals.db_tables import declarative_Base, GDAS_profile, Target
from ASTRA.utils import custom_exceptions

resource_path = Path(__file__).parent.parent / "resources"


class DB_connection:
    """Connection to a database to store internal information."""

    def __init__(self, debug_mode: bool = False) -> None:  # noqa: D107
        """Create database engine and session maker.

        If the database does not exist: create it, alongside the tables
        """
        logger.debug("Launching new DB connection")

        url = "sqlite:///" + (resource_path / "internalSBART.db").as_posix()

        self.engine = create_engine(url, echo=False)
        # drop_database(url)

        # Base.metadata.drop_all(bind=self.engine)
        declarative_Base.metadata.create_all(bind=self.engine)

        if not database_exists(url):
            logger.info("Creating database")
            create_database(url)
        self.sessionmaker = sessionmaker(bind=self.engine)

    ###########################
    #      search data        #
    ###########################

    def get_GDAS_profile(self, gdas_filename: str) -> np.ndarray:
        """Search database for a pre-existing GDAS database for Telfit.

        Raises:
            FileNotFoundError: if gdas_dilename is not yet on disk

        """
        with self.sessionmaker() as session:
            chosen_target = session.query(GDAS_profile).filter_by(gdas_filename=gdas_filename).first()
        if chosen_target is None:
            raise FileNotFoundError("GDAS profile does not exist")

        data_path = resource_path / "atmosphere_profiles" / gdas_filename
        return np.loadtxt(data_path)

    def get_star_params(self, star_name: str) -> dict[str, float]:
        """Get parameters of current star.

        Args:
            star_name (str): star name

        Raises:
            InternalError: Start doesn't exist.

        Returns:
            dict[str, float]: parameters

        """
        with self.sessionmaker() as session:
            chosen_target = session.query(Target).filter_by(name=star_name).first()

        if chosen_target is None:
            raise custom_exceptions.InternalError(f"Target {star_name} does not have cached information")

        return chosen_target.params

    def add_new_star(self, star_name: str, pmra: float, pmdec: float, parallax: float) -> None:
        """Store new star on the DB.

        Args:
            star_name (str): Name of the star
            pmra (float): proper motion RA; from SIMBAD
            pmdec (float): proper motion DEC; from Simbad
            parallax (float): from simbad

        Raises:
            InternalError: If something goes wrong.

        """
        with self.sessionmaker() as session:
            try:
                new_prof = Target(
                    name=star_name,
                    pmra=pmra,
                    pmdec=pmdec,
                    parallax=parallax,
                )
                session.add(new_prof)
                session.commit()
            except Exception as e:
                session.rollback()
                raise custom_exceptions.InternalError from e

    def add_new_profile(self, gdas_filename: str, instrument: str, data: np.ndarray) -> None:
        """Store a new GDAS profile in the DB.

        Args:
            gdas_filename (str): GDAS filename
            instrument (str): instrument
            data (np.ndarray): data

        Raises:
            custom_exceptions.InternalError: If something goes wrong

        """
        with self.sessionmaker() as session:
            try:
                data_path = resource_path / "atmosphere_profiles" / gdas_filename
                np.savetxt(fname=data_path, X=data)

                new_prof = GDAS_profile(
                    gdas_filename=gdas_filename,
                    instrument=instrument,
                    download_date=datetime.datetime.now(),
                )

                logger.info(f"Added new GDAS profile {instrument}")
                session.add(new_prof)
                session.commit()
            except Exception as e:
                session.rollback()
                raise custom_exceptions.InternalError from e

    def delete_all(self) -> None:
        """Drop all tables and create new ones."""
        logger.info("Deleting data from all Tables")
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
