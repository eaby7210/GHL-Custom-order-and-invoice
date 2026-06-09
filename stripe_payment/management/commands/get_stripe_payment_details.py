from django.core.management.base import BaseCommand
import stripe
from django.conf import settings
import json

class Command(BaseCommand):
    help = 'Retrieves and prints details of a Stripe Payment (PaymentIntent, Session, or Event)'

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument('--payment-intent', '-p', type=str, help='The ID of the PaymentIntent to retrieve')
        group.add_argument('--session', '-s', type=str, help='The ID of the Checkout Session to retrieve')
        group.add_argument('--event', '-e', type=str, help='The ID of the Webhook Event to retrieve')
        group.add_argument('--invoice', '-i', type=str, help='The ID of the Invoice to retrieve')
        parser.add_argument(
            '--event-pages',
            type=int,
            default=10,
            metavar='N',
            help=(
                'With -p: max pages (100 events/page, newest first) to scan for '
                'events referencing this PaymentIntent. Default: 10.'
            ),
        )

    def handle(self, *args, **options):
        stripe.api_key = settings.STRIPE_SECRET_KEY

        try:
            if options.get('event'):
                event_id = options['event']
                event = stripe.Event.retrieve(event_id)
                self.stdout.write(self.style.SUCCESS(f"Successfully retrieved Event: {event_id}"))
                self._print_json(event)
                
                # Check if it contains a Checkout Session or PaymentIntent
                if getattr(event, 'data', None) and getattr(event.data, 'object', None):
                    obj = event.data.object
                    if getattr(obj, 'object', None) == 'checkout.session':
                        self.stdout.write(self.style.SUCCESS(f"\nEmbedded Checkout Session Event Date:"))
                        self._print_json(obj)
                        if getattr(obj, 'payment_intent', None):
                            self._retrieve_and_print_payment_intent(
                                obj.payment_intent,
                                event_scan_pages=options['event_pages'],
                            )
                    elif getattr(obj, 'object', None) == 'payment_intent':
                        self.stdout.write(self.style.SUCCESS(f"\nEmbedded PaymentIntent Event Data:"))
                        self._print_json(obj)
            
            elif options.get('session'):
                session_id = options['session']
                session = stripe.checkout.Session.retrieve(session_id)
                self.stdout.write(self.style.SUCCESS(f"Successfully retrieved Checkout Session: {session_id}"))
                self._print_json(session)
                
                if getattr(session, 'payment_intent', None):
                    self._retrieve_and_print_payment_intent(
                        session.payment_intent,
                        event_scan_pages=options['event_pages'],
                    )

            elif options.get('payment_intent'):
                payment_intent_id = options['payment_intent']
                self._retrieve_and_print_payment_intent(
                    payment_intent_id,
                    event_scan_pages=options['event_pages'],
                )

            elif options.get('invoice'):
                invoice_id = options['invoice']
                invoice = stripe.Invoice.retrieve(invoice_id)
                self.stdout.write(self.style.SUCCESS(f"Successfully retrieved Invoice: {invoice_id}"))
                self._print_json(invoice)

                if getattr(invoice, 'payment_intent', None):
                    self._retrieve_and_print_payment_intent(
                        invoice.payment_intent,
                        event_scan_pages=options['event_pages'],
                    )

        except stripe.error.StripeError as e:
            self.stdout.write(self.style.ERROR(f"Stripe Error: {e}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {e}"))
            
    @staticmethod
    def _payment_intent_ref(obj):
        """Resolve payment_intent id from a Stripe object, if present."""
        pi = getattr(obj, 'payment_intent', None)
        if pi is None:
            return None
        if isinstance(pi, str):
            return pi
        return getattr(pi, 'id', None)

    def _event_object_refs_payment_intent(self, obj, pi_id):
        if obj is None:
            return False
        otype = getattr(obj, 'object', None)
        oid = getattr(obj, 'id', None)
        if otype == 'payment_intent' and oid == pi_id:
            return True
        if otype in ('checkout.session', 'charge', 'invoice'):
            return self._payment_intent_ref(obj) == pi_id
        return False

    def _collect_events_for_payment_intent(self, pi_id, max_pages):
        """Scan recent Events (newest first) for payloads that reference pi_id."""
        seen = set()
        matches = []
        starting_after = None
        for page in range(max(1, max_pages)):
            params = {'limit': 100}
            if starting_after:
                params['starting_after'] = starting_after
            page_obj = stripe.Event.list(**params)
            for evt in page_obj.data:
                obj = evt.data.object if evt.data else None
                if not self._event_object_refs_payment_intent(obj, pi_id):
                    continue
                if evt.id in seen:
                    continue
                seen.add(evt.id)
                matches.append({
                    'id': evt.id,
                    'type': getattr(evt, 'type', None),
                    'created': getattr(evt, 'created', None),
                })
            data = page_obj.data or []
            if not getattr(page_obj, 'has_more', False) or not data:
                break
            starting_after = data[-1].id
        return matches

    def _retrieve_and_print_payment_intent(
        self, payment_intent_id, *, event_scan_pages=10,
    ):
        if not isinstance(payment_intent_id, str):
            payment_intent_id = getattr(payment_intent_id, 'id', str(payment_intent_id))

        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        self.stdout.write(self.style.SUCCESS(
            f"\nSuccessfully retrieved PaymentIntent: {payment_intent_id}"
        ))
        self._print_json(intent)

        # All Checkout Sessions that reference this PI (usually 0 or 1).
        session_rows = []
        starting_after = None
        for _ in range(20):
            kw = {'payment_intent': payment_intent_id, 'limit': 100}
            if starting_after:
                kw['starting_after'] = starting_after
            sessions = stripe.checkout.Session.list(**kw)
            session_rows.extend(sessions.data or [])
            if not getattr(sessions, 'has_more', False) or not sessions.data:
                break
            starting_after = sessions.data[-1].id

        if session_rows:
            ids_line = ', '.join(s.id for s in session_rows)
            self.stdout.write(self.style.SUCCESS(
                f"\nCheckout Session ID(s) ({len(session_rows)}): {ids_line}"
            ))
            for sess in session_rows:
                self.stdout.write(self.style.SUCCESS(
                    f"\n--- Checkout Session: {sess.id} ---"
                ))
                self._print_json(sess)
        else:
            self.stdout.write(self.style.WARNING(
                "\nNo related Checkout Session found for this PaymentIntent."
            ))

        events = self._collect_events_for_payment_intent(
            payment_intent_id, event_scan_pages,
        )
        if not events:
            self.stdout.write(self.style.WARNING(
                "\nNo Stripe Events found referencing this PaymentIntent in "
                f"the first {event_scan_pages} page(s) of Event.list (newest "
                "first). Use --event-pages to scan deeper, or the event is "
                "older than scanned range."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\nStripe Event(s) referencing this PaymentIntent ({len(events)}):"
            ))
            self.stdout.write(json.dumps(events, indent=4, default=str))

    def _print_json(self, stripe_obj):
        if hasattr(stripe_obj, 'to_dict_recursive'):
            obj_dict = stripe_obj.to_dict_recursive()
        elif hasattr(stripe_obj, 'to_dict'):
            obj_dict = stripe_obj.to_dict()
        else:
            obj_dict = stripe_obj

        self.stdout.write(json.dumps(obj_dict, indent=4, default=str))
