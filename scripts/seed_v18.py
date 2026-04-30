"""Idempotent seed script for V1.8 intake foundation."""
import os
from sqlalchemy import create_engine, text
from app.config import DATABASE_URL

CATEGORIES = [
    ("PUB-WTR", "public", "Public — Water", "🔵", "water_dept", 10),
    ("PUB-ELC", "public", "Public — Electricity", "🔵", "electricity_dept", 20),
    ("PUB-SAN", "public", "Public — Sanitation", "🔵", "sanitation_dept", 30),
    ("PUB-RNB", "public", "Public — Roads & Buildings", "🔵", "rnb_dept", 40),
    ("PUB-OTH", "public", "Public — Others", "🔵", "pa_inbox", 50),
    ("PRV-POL", "private", "Private — Police", "🟠", "police_liaison", 60),
    ("PRV-REV", "private", "Private — Revenue", "🟠", "revenue_dept", 70),
    ("PRV-WEL", "private", "Private — Welfare", "🟠", "welfare_dept", 80),
    ("PRV-MED", "private", "Private — Medical", "🟠", "medical_liaison", 90),
    ("PRV-EDU", "private", "Private — Education", "🟠", "education_liaison", 100),
    ("PRV-OTH", "private", "Private — Others", "🟠", "pa_inbox", 110),
    ("APT-MTG", "appointment", "Appointment — Meeting Request", "📅", "pa_inbox", 120),
    ("APT-EVT", "appointment", "Appointment — Event Invitation", "📅", "pa_inbox", 130),
    ("APT-FEL", "appointment", "Appointment — Felicitation/Programme", "📅", "pa_inbox", 140),
]

QUEUES = [
    "pa_inbox", "water_dept", "electricity_dept", "sanitation_dept", "rnb_dept",
    "revenue_dept", "welfare_dept", "police_liaison", "medical_liaison", "education_liaison",
    "general_dept", "triage",
]


def seed() -> None:
    engine = create_engine(DATABASE_URL)
    pa_mobile = os.getenv("DEV_OFFICER_MOBILE", "9999999999")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO offices (id) VALUES (1) ON CONFLICT (id) DO NOTHING"))
        for code, group_, name, emoji, queue, sort_order in CATEGORIES:
            conn.execute(text(
                """
                INSERT INTO complaint_categories
                (code, parent_group, display_name_en, icon_emoji, default_routing_queue, sort_order)
                VALUES (:code, :group_, :name, :emoji, :queue, :sort_order)
                ON CONFLICT (code) DO UPDATE SET
                    parent_group = EXCLUDED.parent_group,
                    display_name_en = EXCLUDED.display_name_en,
                    icon_emoji = EXCLUDED.icon_emoji,
                    default_routing_queue = EXCLUDED.default_routing_queue,
                    sort_order = EXCLUDED.sort_order
                """
            ), dict(code=code, group_=group_, name=name, emoji=emoji, queue=queue, sort_order=sort_order))

        mandal_ids = []
        for i in range(1, 6):
            name = f"Test_Mandal_{i}"
            row = conn.execute(text(
                """INSERT INTO mandals (office_id, name, sort_order)
                VALUES (1, :name, :sort_order)
                ON CONFLICT (office_id, name) DO UPDATE SET sort_order = EXCLUDED.sort_order
                RETURNING id"""
            ), {"name": name, "sort_order": i * 10}).fetchone()
            mandal_id = row[0] if row else conn.execute(text("SELECT id FROM mandals WHERE office_id=1 AND name=:name"), {"name": name}).scalar_one()
            mandal_ids.append(mandal_id)

        ward_names = ["Madhapur", "Gachibowli", "Kondapur", "Nallagandla", "Lingampally", "Miyapur"]
        for idx, mandal_id in enumerate(mandal_ids, start=1):
            for ward_no in range(1, 7):
                lat = 17.300000 + (idx * 0.03) + (ward_no * 0.002)
                lng = 78.300000 + (idx * 0.04) + (ward_no * 0.003)
                conn.execute(text(
                    """INSERT INTO wards (office_id, mandal_id, ward_number, ward_name, centroid_lat, centroid_lng)
                    VALUES (1, :mandal_id, :ward_number, :ward_name, :lat, :lng)
                    ON CONFLICT (office_id, mandal_id, ward_number)
                    DO UPDATE SET ward_name=EXCLUDED.ward_name, centroid_lat=EXCLUDED.centroid_lat, centroid_lng=EXCLUDED.centroid_lng"""
                ), {"mandal_id": mandal_id, "ward_number": ward_no, "ward_name": ward_names[ward_no - 1], "lat": lat, "lng": lng})

        for queue in QUEUES:
            mobile = pa_mobile if queue == "pa_inbox" else "9999999999"
            existing = conn.execute(text("SELECT id FROM officer_mappings WHERE office_id=1 AND queue_name=:queue_name AND is_default_for_queue=TRUE LIMIT 1"), {"queue_name": queue}).fetchone()
            if existing:
                conn.execute(text("UPDATE officer_mappings SET officer_contact_value=:mobile, officer_name=:name, department=:department WHERE id=:id"), {
                    "id": existing[0],
                    "department": queue,
                    "name": f"{queue}_officer",  # TODO: replace with real officer data before pilot
                    "mobile": mobile,
                })
            else:
                conn.execute(text("""INSERT INTO officer_mappings (department, ward, officer_name, officer_contact_type, officer_contact_value, office_id, queue_name, is_default_for_queue)
                VALUES (:department, 'ALL', :name, 'phone', :mobile, 1, :queue_name, TRUE)"""), {
                    "department": queue,
                    "name": f"{queue}_officer",  # TODO: replace with real officer data before pilot
                    "mobile": mobile,
                    "queue_name": queue,
                })

if __name__ == "__main__":
    seed()
    print("seed_v18 complete")
