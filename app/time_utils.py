# Manila time fixed offset +8. Walang DST ang Pilipinas, kaya
# hindi na kailangan ng IANA timezone files sa Windows.
from datetime import timedelta, timezone


MANILA_TZ = timezone(timedelta(hours=8), name="Asia/Manila")
