from datetime import datetime, date

PRICING_EVENTS = [
    {
        "name": "Keukenhof 2025",
        "start_date": date(2025, 3, 20),
        "end_date": date(2025, 5, 12),
        "uplift_percentage": 25,
        "event_type": "seasonal"
    },
    {
        "name": "F1 Dutch Grand Prix 2025", 
        "start_date": date(2025, 8, 29),
        "end_date": date(2025, 8, 31),
        "uplift_percentage": 50,
        "event_type": "major_event"
    },
    {
        "name": "Amsterdam Dance Event 2025",
        "start_date": date(2025, 10, 15), 
        "end_date": date(2025, 10, 19),
        "uplift_percentage": 35,
        "event_type": "major_event"
    },
    {
        "name": "Keukenhof 2026",
        "start_date": date(2026, 3, 19),
        "end_date": date(2026, 5, 10), 
        "uplift_percentage": 25,
        "event_type": "seasonal"
    }
]

def get_event_uplift(check_date):
    """Get pricing uplift for a specific date"""
    if isinstance(check_date, str):
        check_date = datetime.strptime(check_date, '%Y-%m-%d').date()
    
    for event in PRICING_EVENTS:
        if event["start_date"] <= check_date <= event["end_date"]:
            return event["uplift_percentage"], event["name"]
    
    return 0, None