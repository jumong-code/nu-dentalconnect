from datetime import timedelta, timezone


# Manila uses UTC+08:00 without daylight-saving changes. A fixed-offset timezone
# avoids requiring external IANA timezone database files on Windows.
MANILA_TZ = timezone(timedelta(hours=8), name="Asia/Manila")
