from db import create_tables, get_last_fetched_hour, set_last_fetched_hour, save_event, get_connection
from poller import fetch_file
from normalizer import parse_file, parse_event, normalize
from datetime import datetime, timedelta
import os


if __name__ == "__main__":

    # יצירת כל הטבלאות אם לא קיימות
    create_tables()

    # בדיקה עד לאיזה קובץ כבר הורדנו בעבר
    last_hour = get_last_fetched_hour()

    # קריאת תאריך ההתחלה מה-environment
    start = os.environ.get('REPLAY_WINDOW_START', '2024-01-15')

    # אם אין high-water mark — מתחילים מהתחלה. אחרת ממשיכים מהשעה ש*אחרי*
    # האחרונה שהושלמה — אחרת היינו מושכים ומכניסים שוב שעה שכבר נשמרה (כפילויות).
    if last_hour is None:
        current_hour = datetime.strptime(start + '-0', '%Y-%m-%d-%H')
    else:
        current_hour = datetime.strptime(last_hour, '%Y-%m-%d-%H') + timedelta(hours=1)


    while True:
        # נסה להוריד את הקובץ של השעה הנוכחית
        print(f"Fetching {current_hour}", flush=True)
        response = fetch_file(current_hour)

        # אם קיבלנו None — ה-vendor החזיר 404 או 503, ה-poller כבר ישן. ננסה שוב
        if response is None:
            continue

        # פתח את ה-gzip וחלק לשורות
        lines = parse_file(response)
        print(f"Got {len(lines)} lines to process", flush=True)

        # connection אחד לכל שעה — נסגור רק אחרי שכל השורות נשמרו
        conn = get_connection()
        for line in lines:
            event = parse_event(line)
            if event is None:
                continue
            normalized = normalize(event)
            if normalized is None:
                continue
            try:
                save_event(normalized, conn)
            except Exception as e:
                print(f"Skipping bad event: {e}", flush=True)
                conn.rollback()
        conn.commit()
        conn.close()

        # עדכן high-water mark לשעה שסיימנו
        hour_str = f"{current_hour.year}-{current_hour.month}-{current_hour.day}-{current_hour.hour}"
        set_last_fetched_hour(hour_str)

        # עבור לשעה הבאה
        current_hour = current_hour + timedelta(hours=1)
