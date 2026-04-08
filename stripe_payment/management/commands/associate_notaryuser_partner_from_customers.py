"""
Link ``NotaryUser.partner`` from ``tolt.Customer`` when emails match.

For each eligible ``NotaryUser``, finds a ``Customer`` with the same email
(case-insensitive) and a non-null ``partner``, then sets ``notary_user.partner``.

Then prints ``Customer`` rows whose email does not match any ``NotaryUser`` email.
"""

from django.core.management.base import BaseCommand
from django.db.models import Q

from stripe_payment.models import NotaryUser
from tolt.models import Customer


class Command(BaseCommand):
    help = (
        "Set NotaryUser.partner from Tolt Customer with matching email; "
        "list Customers with no NotaryUser sharing that email."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show updates only; do not save NotaryUser rows.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Also update NotaryUser rows that already have a partner.",
        )
        parser.add_argument(
            "--skip-associate",
            action="store_true",
            help=(
                "Only print Customers without a matching NotaryUser (no updates)."
            ),
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        force = options["force"]
        skip_associate = options["skip_associate"]

        if not skip_associate:
            qs = NotaryUser.objects.all().order_by("id")
            if not force:
                qs = qs.filter(partner__isnull=True)

            updated = 0
            skipped_no_email = 0
            skipped_no_customer = 0
            skipped_no_partner_on_customer = 0
            ambiguous = 0

            for nu in qs.iterator(chunk_size=500):
                email = (nu.email or "").strip()
                if not email:
                    skipped_no_email += 1
                    continue

                c_base = Customer.objects.filter(email__iexact=email)
                candidates = list(
                    c_base.exclude(partner_id__isnull=True).order_by("id")
                )
                if not candidates:
                    if c_base.exists():
                        skipped_no_partner_on_customer += 1
                    else:
                        skipped_no_customer += 1
                    continue

                partner_ids = {c.partner_id for c in candidates}
                if len(partner_ids) > 1:
                    ambiguous += 1
                    first_id = candidates[0].id
                    self.stdout.write(
                        self.style.WARNING(
                            f"NotaryUser id={nu.id} email={email!r}: "
                            f"multiple Customers, partner_ids {partner_ids}; "
                            f"using first customer id={first_id}"
                        )
                    )

                partner = candidates[0].partner
                if not partner:
                    skipped_no_partner_on_customer += 1
                    continue

                if not dry_run:
                    nu.partner = partner
                    nu.save(update_fields=["partner"])

                updated += 1
                action = "[dry-run] would set" if dry_run else "set"
                cid = candidates[0].id
                self.stdout.write(
                    f"  {action} NotaryUser id={nu.id} ({email}) "
                    f"partner_id={partner.id} from Customer id={cid}"
                )

            self.stdout.write("")
            summary = (
                "Association summary: "
                f"updated={updated}, "
                f"skipped_no_email={skipped_no_email}, "
                f"skipped_no_matching_customer={skipped_no_customer}, "
                f"customer_exists_but_no_partner="
                f"{skipped_no_partner_on_customer}, "
                f"ambiguous_multi_partner={ambiguous}"
            )
            self.stdout.write(self.style.SUCCESS(summary))
            self.stdout.write("")

        hdr = "Customers with no NotaryUser for same email:"
        self.stdout.write(self.style.NOTICE(hdr))
        orphan_qs = (
            Customer.objects.exclude(Q(email__isnull=True) | Q(email=""))
            .order_by("id")
        )
        nu_emails = set(
            NotaryUser.objects.exclude(email__isnull=True)
            .values_list("email", flat=True)
        )
        nu_lower = {e.strip().lower() for e in nu_emails if e and str(e).strip()}

        orphan_count = 0
        for cust in orphan_qs.iterator(chunk_size=500):
            em = (cust.email or "").strip()
            if not em:
                continue
            if em.lower() not in nu_lower:
                orphan_count += 1
                partner_id = cust.partner_id or ""
                self.stdout.write(
                    f"  customer id={cust.id} email={cust.email!r} "
                    f"partner_id={partner_id}"
                )

        total_msg = (
            f"Total customers without matching NotaryUser: {orphan_count}"
        )
        self.stdout.write(self.style.SUCCESS(total_msg))
