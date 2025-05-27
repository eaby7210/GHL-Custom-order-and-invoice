from django.core.management.base import BaseCommand
from core.models import OAuthToken, Contact, Task, GHLUser
from core.services import TaskServices
from django.db.models import Q, Count, Prefetch, Sum
from core.serializers import ContactSerializer
import json
from django.utils.dateparse import parse_datetime

class Command(BaseCommand):
    help = "Pull tasks for a selected LocationId from existing OAuthToken entries"

    def handle(self, *args, **options):
        BOLD = "\033[1m"
        END = "\033[0m"
        GREEN = "\033[92m"
        RED = "\033[91m"
        CYAN = "\033[96m"
        YELLOW = "\033[93m"

        contacts_t = (
            Contact.objects
                .filter(location_id='1XYDcIkUrFWFYq7nHqF6')
                .filter(Q(phone__isnull=False) | Q(email__isnull=False))
                .annotate(task_count=Count('tasks'))
                .filter(task_count__gt=0)
                .prefetch_related('tasks')
        )

        total_match_count = 0
        serializer = ContactSerializer(contacts_t, many=True)
        contacts_data = serializer.data

        print(f"{BOLD}{CYAN}Total contacts: {len(contacts_data)}{END}")
        print(f"{BOLD}{CYAN}Total task count: {contacts_t.aggregate(total=Sum('task_count'))['total']}{END}\n")

        for i, contact in enumerate(contacts_data, 1):
            email = contact.get("email")
            phone = contact.get("phone")
            contact_id = contact.get("id")
            location_id = contact.get("location_id")

            if not email and not phone:
                continue

            print(f"{BOLD}▶ Contact #{i}: {contact['id']} {contact['first_name']} {contact['last_name']} {email or phone}{END}")
            target_location_id = 'HBMH06bPfTaKkZx49Y4x'
            filter_q = ~Q(id=contact_id) & Q(location_id=target_location_id)
            if email and phone:
                filter_q &= Q(email=email, phone=phone)
            elif email:
                filter_q &= Q(email=email)
            elif phone:
                filter_q &= Q(phone=phone)

            match = Contact.objects.filter(filter_q)
            if match.exists():
                print(f"{YELLOW}→ Matching contacts found in DB.{END}")
                target_contact = match.first()
                target_tasks = TaskServices.get_task_list(target_contact.location_id, target_contact)
                source_tasks = contact.get("tasks", [])

                print(f"{CYAN}Source Tasks ({len(source_tasks)}):{END}")
                # print(f"source task:\n{json.dumps(source_tasks, indent=4)}")
                for idx, source_task in enumerate(source_tasks, 1):
                    source_title = source_task.get("title", "").strip()
                    source_due_raw = source_task.get("due_date")
                    source_due = parse_datetime(source_due_raw) if source_due_raw else None
                    source_body = source_task.get("body", "").strip()

                    found_match = False
                    print(f"\n{BOLD}Task #{idx}: {source_title} ({source_due}){END}")
                    for target_task in target_tasks:
                        target_title = target_task.get("title", "").strip()
                        target_due = parse_datetime(target_task.get("dueDate")) if target_task.get("dueDate") else None
                        target_body = target_task.get("body").strip() if target_task.get("body") else ""

                        title_match = source_title == target_title
                        due_match = source_due == target_due
                        body_match = source_body == target_body

                        # print(f"   ➤ Title Match: {GREEN if title_match else RED}{title_match}{END} ({source_title} vs {target_title})")
                        # print(f"   ➤ Due Date Match: {GREEN if due_match else RED}{due_match}{END} ({source_due} vs {target_due})")
                        # print(f"   ➤ Body Match: {GREEN if body_match else RED}{body_match}{END} ({source_body} vs {target_body})")

                        if title_match and due_match and body_match:
                            print(f"{GREEN}    ✅ Matching task found.{END}")
                            found_match = True
                            break

                    if not found_match:
                        print(f"{RED}    ❌ No matching task found for: {source_title}{END}")
                        print("Creating new task using API...")
                        s_ghluser = GHLUser.objects.filter(id=source_task['assigned_to']).first()
                        ghluser = GHLUser.objects.filter(
                            last_name=s_ghluser.last_name,first_name=s_ghluser.first_name
                            ).exclude(
                                id=s_ghluser.id
                                ).first()
                        print(source_task['assigned_to'], ghluser, s_ghluser)
                        task_payload = {
                            "title": source_task.get("title", "").strip(),
                            "dueDate": source_due_raw,
                            "body": source_body,
                            "completed": source_task.get("conpleted",False),
                            "assignedTo": ghluser.id
                            
                        }

                        result = TaskServices.post_task(
                            target_location_id,
                            target_contact.id,
                            task_payload
                        )

                        if result:
                            print(f"{GREEN}    ✅ Task created successfully for contact {target_contact.id}{END}")
                        else:
                            print(f"{RED}    ❌ Task creation failed for contact {target_contact.id}{END}")

                                            
                        
            else:
                print(f"{RED}→ No matching contact found.{END}")
                print("Creating contact and tasks using API...")

                from core.services import ContactServices
                new_contact_id = ContactServices.create_contact_with_tasks(contact, target_location_id)

                if new_contact_id:
                    print(f"{GREEN}✔ Contact and tasks migrated successfully.{END}")

            total_match_count += match.count()

        print(f"\n{BOLD}{YELLOW}Total matched contact count: {total_match_count}{END}")
