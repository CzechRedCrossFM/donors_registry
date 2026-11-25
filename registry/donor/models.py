import re

from sqlalchemy import case, func, select

from registry.database import czech_order, timestamp_type
from registry.extensions import db
from registry.list.models import DonationCenter, Medals
from registry.utils import (
    EMAIL_RE,
    capitalize,
    format_postal_code,
    split_degrees,
)


class Batch(db.Model):
    __tablename__ = "batches"
    id = db.Column(db.Integer, primary_key=True)
    donation_center_id = db.Column(db.ForeignKey(DonationCenter.id))
    donation_center = db.relationship("DonationCenter")
    imported_at = db.Column(timestamp_type, nullable=False)

    def __repr__(self):
        return f"<Batch({self.id}) from {self.imported_at}>"


class Record(db.Model):
    __tablename__ = "records"
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.ForeignKey(Batch.id, ondelete="CASCADE"), nullable=False)
    batch = db.relationship("Batch")
    rodne_cislo = db.Column(db.Unicode(10), index=True, nullable=False)
    first_name = db.Column(db.Unicode, nullable=False)
    last_name = db.Column(db.Unicode, nullable=False)
    address = db.Column(db.Unicode, nullable=False)
    city = db.Column(db.Unicode, nullable=False)
    postal_code = db.Column(db.Unicode(5), nullable=False)
    kod_pojistovny = db.Column(db.Unicode(3), nullable=False)
    donation_count = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f"<Record({self.id}) {self.rodne_cislo} from Batch {self.batch}>"

    @classmethod
    def from_list(cls, list):
        return cls(
            batch_id=list[0],
            rodne_cislo=list[1],
            first_name=list[2],
            last_name=list[3],
            address=list[4],
            city=list[5],
            postal_code=list[6],
            kod_pojistovny=list[7],
            donation_count=list[8],
        )


def latest_donation_records(cutoff=None, rodne_cislo=None):
    """Rank each donor's records by recency, both overall and per center."""
    order = (Batch.imported_at.desc(), Record.donation_count.desc(), Record.id.desc())
    query = (
        select(
            *Record.__table__.columns,
            Batch.donation_center_id,
            DonationCenter.slug,
            func.row_number()
            .over(
                partition_by=(Record.rodne_cislo, Batch.donation_center_id),
                order_by=order,
            )
            .label("center_rank"),
            func.row_number()
            .over(partition_by=Record.rodne_cislo, order_by=order)
            .label("person_rank"),
        )
        .join(Batch, Batch.id == Record.batch_id)
        .outerjoin(DonationCenter, DonationCenter.id == Batch.donation_center_id)
    )
    if cutoff is not None:
        query = query.where(Batch.imported_at <= cutoff)
    if rodne_cislo:
        query = query.where(Record.rodne_cislo == rodne_cislo)
    return query.subquery()


class IgnoredDonors(db.Model):
    __tablename__ = "ignored_donors"
    rodne_cislo = db.Column(db.Unicode(10), primary_key=True)
    reason = db.Column(db.Unicode, nullable=False)
    ignored_since = db.Column(timestamp_type, nullable=False)


class AwardedMedals(db.Model):
    __tablename__ = "awarded_medals"
    rodne_cislo = db.Column(db.Unicode(10), index=True, nullable=False)
    medal_id = db.Column(db.ForeignKey(Medals.id))
    medal = db.relationship("Medals")
    # NULL means unknown data - imported from the old system
    awarded_at = db.Column(timestamp_type, nullable=True)
    __table_args__ = (db.PrimaryKeyConstraint("rodne_cislo", "medal_id"),)


class AwardEligibilitySnapshot(db.Model):
    """Stores eligible donors for annual medal awards.

    For higher-value medals (gold and above), we need to know who was eligible
    based on donations from the previous year. This table stores a snapshot of
    eligible rodne_cislo values for a given medal and year.
    """

    __tablename__ = "award_eligibility_snapshots"
    medal_id = db.Column(db.ForeignKey(Medals.id), nullable=False)
    medal = db.relationship("Medals")
    year = db.Column(db.Integer, nullable=False)
    rodne_cislo = db.Column(db.Unicode(10), nullable=False)
    created_at = db.Column(timestamp_type, nullable=False)
    __table_args__ = (db.PrimaryKeyConstraint("medal_id", "year", "rodne_cislo"),)

    @classmethod
    def create_snapshot(cls, medal, year):
        """Create a snapshot of eligible donors for the given medal and year.

        The snapshot uses donation counts as of the creation time (now).
        Only checks donors who are currently eligible (not already awarded),
        then verifies they were also eligible on the cutoff date.

        Args:
            medal: Medals object
            year: Year for which awards are being prepared (e.g., 2026)

        Returns:
            Number of eligible donors found
        """
        from datetime import datetime

        # Check if snapshot already exists for this medal/year
        existing = cls.query.filter_by(medal_id=medal.id, year=year).first()
        if existing:
            # Snapshot already created, return count (excluding marker)
            all_entries = cls.query.filter_by(medal_id=medal.id, year=year).all()
            return len([e for e in all_entries if e.rodne_cislo != "__EMPTY__"])

        # Cutoff date is now (when snapshot is created)
        cutoff_datetime = datetime.now()

        latest = latest_donation_records(cutoff=cutoff_datetime)
        eligible = (
            select(latest.c.rodne_cislo)
            .join(DonorsOverview, DonorsOverview.rodne_cislo == latest.c.rodne_cislo)
            .where(
                latest.c.center_rank == 1,
                DonorsOverview.donation_count_total >= medal.minimum_donations,
                getattr(DonorsOverview, "awarded_medal_" + medal.slug) == db.false(),
            )
            .group_by(latest.c.rodne_cislo)
            .having(func.sum(latest.c.donation_count) >= medal.minimum_donations)
        )
        eligible_rodne_cisla = db.session.scalars(eligible).all()
        if not eligible_rodne_cisla:
            db.session.add(
                cls(
                    medal_id=medal.id,
                    year=year,
                    rodne_cislo="__EMPTY__",
                    created_at=cutoff_datetime,
                )
            )

        # Store the snapshot
        for rodne_cislo in eligible_rodne_cisla:
            snapshot = cls(
                medal_id=medal.id,
                year=year,
                rodne_cislo=rodne_cislo,
                created_at=cutoff_datetime,
            )
            db.session.add(snapshot)

        db.session.commit()
        return len(eligible_rodne_cisla)

    @classmethod
    def get_eligible_rodne_cisla(cls, medal_id, year):
        """Get list of eligible rodne_cislo for a medal and year.

        Returns:
            List of rodne_cislo strings, or None if snapshot doesn't exist
        """
        # Check if snapshot was ever created (even if empty)
        snapshot_exists = (
            cls.query.filter_by(medal_id=medal_id, year=year).first() is not None
        )

        if not snapshot_exists:
            return None

        # Return all eligible rodne_cisla (excluding marker for empty snapshots)
        snapshots = cls.query.filter_by(medal_id=medal_id, year=year).all()
        return [s.rodne_cislo for s in snapshots if s.rodne_cislo != "__EMPTY__"]


class DonorsOverview(db.Model):
    __tablename__ = "donors_overview"
    rodne_cislo = db.Column(db.Unicode(10), primary_key=True)
    first_name = db.Column(db.Unicode, nullable=False)
    last_name = db.Column(db.Unicode, nullable=False)
    address = db.Column(db.Unicode, nullable=False)
    city = db.Column(db.Unicode, nullable=False)
    postal_code = db.Column(db.Unicode(5), nullable=False)
    kod_pojistovny = db.Column(db.Unicode(3), nullable=False)
    donation_count_fm = db.Column(db.Integer, nullable=False)
    donation_count_fm_bubenik = db.Column(db.Integer, nullable=False)
    donation_count_trinec = db.Column(db.Integer, nullable=False)
    donation_count_mp = db.Column(db.Integer, nullable=False)
    donation_count_manual = db.Column(db.Integer, nullable=False)
    donation_count_total = db.Column(db.Integer, nullable=False)
    awarded_medal_br = db.Column(db.Boolean, nullable=False)
    awarded_medal_st = db.Column(db.Boolean, nullable=False)
    awarded_medal_zl = db.Column(db.Boolean, nullable=False)
    awarded_medal_kr3 = db.Column(db.Boolean, nullable=False)
    awarded_medal_kr2 = db.Column(db.Boolean, nullable=False)
    awarded_medal_kr1 = db.Column(db.Boolean, nullable=False)
    awarded_medal_plk = db.Column(db.Boolean, nullable=False)
    note = db.relationship(
        "Note",
        uselist=False,
        primaryjoin="foreign(DonorsOverview.rodne_cislo) == Note.rodne_cislo",
    )

    frontend_column_names = {
        "rodne_cislo": "Rodné číslo",
        "first_name": "Jméno",
        "last_name": "Příjmení",
        "address": "Adresa",
        "city": "Město",
        "postal_code": "PSČ",
        "kod_pojistovny": "Pojišťovna",
        "donations": "Darování Celkem",
        "last_award": "Ocenění",
        "note": "Pozn.",
    }

    # Fields for frontend not calculated from multiple columns
    basic_fields = [
        c
        for c in frontend_column_names.keys()
        if c not in ("donations", "last_award", "note")
    ]

    def __repr__(self):
        return f"<DonorsOverview ({self.rodne_cislo})>"

    @classmethod
    def get_filter_for_search(cls, search_str):
        conditions_all = []
        for part in search_str.split():
            conditions_all.append([])
            for column_name in cls.frontend_column_names.keys():
                if hasattr(cls, column_name):
                    if column_name == "note":
                        column = Note.note
                    else:
                        column = getattr(cls, column_name)
                    contains = getattr(column, "contains")
                    conditions_all[-1].append(contains(part, autoescape=True))
        return db.and_(*[db.or_(*conditions) for conditions in conditions_all])

    @classmethod
    def get_order_by_for_column_id(cls, column_id, direction):
        column_name = list(cls.frontend_column_names.keys())[column_id]
        if hasattr(cls, column_name):
            column = getattr(cls, column_name)
            column_with_collation = czech_order(column)
            return (getattr(column_with_collation, direction)(),)
        elif column_name == "donations":
            column_name = "donation_count_total"
            column = getattr(cls, column_name)
            return (getattr(column, direction)(),)
        elif column_name == "last_award":
            order_by = []
            for medal in Medals.query.order_by(Medals.id.asc()).all():
                column = getattr(cls, "awarded_medal_" + medal.slug)
                order_by.append(getattr(column, direction)())
            return order_by

    def dict_for_frontend(self):
        # All standard attributes
        donor_dict = {}
        for name in self.frontend_column_names.keys():
            donor_dict[name] = getattr(self, name, None)
            # Note is special because note column contains
            # Note object but we need to get its text which
            # is in Note.note attr. We send it as structured data
            # so the frontend can display different icons for different types.
            if donor_dict[name] is not None and name == "note":
                note_obj = donor_dict[name]
                emails = note_obj.get_emails_from_note()
                phones = note_obj.get_phones_from_note()

                # Calculate "other text" by removing emails and phones
                other_text = note_obj.note
                for email in emails:
                    other_text = other_text.replace(email, "")
                for phone in phones:
                    other_text = other_text.replace(phone, "")
                # Clean up whitespace
                other_text = "\n".join(
                    line.strip() for line in other_text.split("\n") if line.strip()
                )

                donor_dict[name] = {
                    "emails": emails,
                    "phones": phones,
                    "other": other_text,
                    "raw": note_obj.note,  # Keep full text for fallback
                }
            elif donor_dict[name] is not None and name in (
                "first_name",
                "last_name",
                "address",
                "city",
            ):
                donor_dict[name] = capitalize(donor_dict[name])

        # Highest awarded medal
        for medal in Medals.query.order_by(Medals.id.desc()).all():
            if getattr(self, "awarded_medal_" + medal.slug):
                donor_dict["last_award"] = medal.title
                break
            else:
                donor_dict["last_award"] = "Žádné"
        # Dict with all donations which we use on frontend
        # to generate tooltip
        donor_dict["donations"] = {
            dc.slug: {
                "count": getattr(self, "donation_count_" + dc.slug),
                "name": dc.title,
            }
            for dc in DonationCenter.query.all()
        }
        donor_dict["donations"]["manual"] = {
            "count": self.donation_count_manual,
            "name": "Jinde",
        }
        donor_dict["donations"]["total"] = self.donation_count_total

        # Format the donor's postal code
        donor_dict["postal_code"] = format_postal_code(self.postal_code)
        return donor_dict

    @classmethod
    def refresh_overview(cls, rodne_cislo=None):
        if rodne_cislo:
            Record.query.filter_by(rodne_cislo=rodne_cislo).first_or_404()
            cls.query.filter_by(rodne_cislo=rodne_cislo).delete()
        else:
            cls.query.delete()

        latest = latest_donation_records(rodne_cislo=rodne_cislo)
        counts = [
            func.sum(
                case((latest.c.slug == slug, latest.c.donation_count), else_=0)
            ).label("donation_count_" + slug)
            for slug in ("fm", "fm_bubenik", "trinec", "mp")
        ]
        counts.append(
            func.sum(
                case(
                    (latest.c.donation_center_id.is_(None), latest.c.donation_count),
                    else_=0,
                )
            ).label("donation_count_manual")
        )
        counts.append(func.sum(latest.c.donation_count).label("donation_count_total"))
        totals = (
            select(latest.c.rodne_cislo, *counts)
            .where(latest.c.center_rank == 1)
            .group_by(latest.c.rodne_cislo)
            .subquery()
        )
        personal_fields = [
            "first_name",
            "last_name",
            "address",
            "city",
            "postal_code",
            "kod_pojistovny",
        ]
        values = [latest.c.rodne_cislo]
        values.extend(
            func.coalesce(getattr(DonorsOverride, field), latest.c[field])
            for field in personal_fields
        )
        values.extend(totals.c[column.name] for column in counts)
        medal_fields = [
            column.name
            for column in cls.__table__.columns
            if column.name.startswith("awarded_medal_")
        ]
        for field in medal_fields:
            awarded = (
                select(AwardedMedals.rodne_cislo)
                .join(Medals)
                .where(
                    AwardedMedals.rodne_cislo == latest.c.rodne_cislo,
                    Medals.slug == field.removeprefix("awarded_medal_"),
                )
                .exists()
            )
            values.append(case((awarded, True), else_=False))
        query = (
            select(*values)
            .join(totals, totals.c.rodne_cislo == latest.c.rodne_cislo)
            .outerjoin(
                DonorsOverride, DonorsOverride.rodne_cislo == latest.c.rodne_cislo
            )
            .where(
                latest.c.person_rank == 1,
                ~latest.c.rodne_cislo.in_(select(IgnoredDonors.rodne_cislo)),
            )
        )
        columns = [
            "rodne_cislo",
            *personal_fields,
            *[column.name for column in counts],
            *medal_fields,
        ]
        db.session.execute(cls.__table__.insert().from_select(columns, query))
        db.session.flush()

        # Code moving degrees from last_name to first_name.
        if rodne_cislo:
            donors_with_degrees = (db.session.get(DonorsOverview, rodne_cislo),)
        else:
            # Because only 4 % of donors have a degree, it makes
            # sense to pre-select them via this query.
            donors_with_degrees = DonorsOverview.query.filter(
                db.or_(
                    DonorsOverview.last_name.contains(" "),
                    DonorsOverview.last_name.contains("."),
                    DonorsOverview.last_name.contains(","),
                )
            ).all()

        for donor in donors_with_degrees:
            last_name, degrees = split_degrees(donor.last_name)
            if degrees:
                donor.first_name = degrees + " " + donor.first_name
                donor.last_name = last_name
                db.session.add(donor)

        db.session.commit()


class Note(db.Model):
    __tablename__ = "notes"
    rodne_cislo = db.Column(db.Unicode(10), primary_key=True)
    note = db.Column(db.UnicodeText)

    def __repr__(self):
        return f"<Note for {self.rodne_cislo}: {self.note}>"

    def get_emails_from_note(self):
        return re.findall(EMAIL_RE, self.note)

    def get_phones_from_note(self):
        """Extract all phone numbers from note."""
        from registry.utils import PHONE_RE

        return re.findall(PHONE_RE, self.note)

    def get_all_contacts(self):
        """Get structured contact information from note."""
        return {
            "emails": self.get_emails_from_note(),
            "phones": self.get_phones_from_note(),
        }


class DonorsOverride(db.Model):
    __tablename__ = "donors_override"
    rodne_cislo = db.Column(db.Unicode(10), primary_key=True)
    first_name = db.Column(db.Unicode)
    last_name = db.Column(db.Unicode)
    address = db.Column(db.Unicode)
    city = db.Column(db.Unicode)
    postal_code = db.Column(db.Unicode(5))
    kod_pojistovny = db.Column(db.Unicode(3))

    def to_dict(self):
        result = {}
        for field in DonorsOverview.basic_fields:
            if getattr(self, field) is not None:
                result[field] = str(getattr(self, field))
            else:
                result[field] = None

        return result


class ContactImportLog(db.Model):
    """Audit log for contact imports."""

    __tablename__ = "contact_import_logs"
    id = db.Column(db.Integer, primary_key=True)
    imported_at = db.Column(timestamp_type, nullable=False)
    imported_by_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    imported_by_user = db.relationship("User")
    filename = db.Column(db.Unicode, nullable=True)  # Null if pasted directly
    input_data = db.Column(db.UnicodeText, nullable=False)
    processed_lines_count = db.Column(db.Integer, nullable=False)
    created_notes_count = db.Column(db.Integer, nullable=False, default=0)
    updated_notes_count = db.Column(db.Integer, nullable=False, default=0)
    emails_added_count = db.Column(db.Integer, nullable=False, default=0)
    phones_added_count = db.Column(db.Integer, nullable=False, default=0)

    def __repr__(self):
        return f"<ContactImportLog({self.id}) at {self.imported_at}>"
