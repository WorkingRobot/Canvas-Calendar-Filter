import httpx
import icalendar
import re
import pytz

from datetime import date
from datetime import datetime

from sanic import Sanic
from sanic import response
from sanic import exceptions

from urllib.parse import unquote

app = Sanic("Canvas-Calendar-Filter")
app.config.OAS = False

# https://codereview.stackexchange.com/a/235478
def is_valid_hostname(hostname: str) -> bool:
    if not 1 < len(hostname) < 253:
        return False

    # Remove trailing dot
    if hostname[-1] == '.':
        hostname = hostname[0:-1]

    #  Split hostname into list of DNS labels
    labels = hostname.split('.')

    #  Define pattern of DNS label
    #  Can begin and end with a number or letter only
    #  Can contain hyphens, a-z, A-Z, 0-9
    #  1 - 63 chars allowed
    fqdn = re.compile(r'^[a-z0-9]([a-z-0-9-]{0,61}[a-z0-9])?$', re.IGNORECASE)

    # Check that all labels match that pattern.
    return all(fqdn.match(label) for label in labels)

def get_due_date(ddd: icalendar.vDDDTypes, tz: pytz.BaseTzInfo) -> datetime:
    dt = ddd.dt
    if isinstance(dt, datetime):
        return dt
    if isinstance(dt, date): # 11:59 PM
        ret = datetime.combine(dt, datetime.max.time().replace(second = 0, microsecond = 0))
        ret = tz.localize(ret)
        ret = tz.normalize(ret)
        ret = ret.astimezone(pytz.utc)
        return ret
    raise ValueError(f"Can't convert {dt} ({type(dt)}).")

def filter_hostname(hostname: str) -> bool:
    if hostname.endswith('.edu'):
        return True
    if hostname.endswith('.instructure.com'):
        return True
    return False

def filter_uid_startswith(prefix: str):
    return lambda evt: evt['UID'].casefold().startswith(prefix.casefold())

def filter_intersect(filter1, filter2):
    return lambda evt: filter1(evt) and filter2(evt)

def filter_not(filt):
    return lambda evt: not filt(evt)

CALENDAR_FILTERS = {
    'calendar-events': filter_uid_startswith('event-calendar-event'),
    'assignments': filter_uid_startswith('event-assignment'),
    'override-assignments': filter_uid_startswith('event-assignment-override'),
    'turn-in-assignments': filter_intersect(filter_uid_startswith('event-assignment'), filter_not(filter_uid_startswith('event-assignment-override')))
}

@app.get('/feeds/<filt:slug>/<tz_name:str>/<hostname:str>/<file=str:ext=ics>')
async def calendar(request, filt: str, tz_name: str, hostname: str, file: str, ext: str):
    filt = filt.lower()
    if filt not in CALENDAR_FILTERS:
        raise exceptions.BadRequest(f"Invalid filter. Must be one of: {', '.join(CALENDAR_FILTERS.keys())}.", context = { "filter": filt })
    
    tz_name = unquote(tz_name)
    try:
        tz = pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError as exc:
        raise exceptions.BadRequest("Invalid timezone.", context = { "tz": tz_name }) from exc
    
    hostname = hostname.lower()
    if not is_valid_hostname(hostname):
        raise exceptions.BadRequest(f"Invalid FQDN hostname.", context = { "hostname": hostname })
    if not filter_hostname(hostname):
        raise exceptions.BadRequest("Hostname isn't allowed. Only *.edu and *.instructure.com are allowed. If your school doesn't use these two, create a GitHub issue to allow it.", context = { "hostname": hostname })
    
    if ext != 'ics':
        raise exceptions.BadRequest("Only .ics files are allowed. Make sure your URL ends with .ics.", context = { "file": file, "ext": ext })

    event_filter = CALENDAR_FILTERS[filt]
    cal_link = f"https://{hostname}/feeds/calendars/{file}.ics"

    try:
        async with httpx.AsyncClient(http2 = True) as client:
            resp = await client.get(cal_link)
            data = await resp.aread()
    except httpx.RequestError as exc:
        raise exceptions.ServiceUnavailable("Failed to fetch calendar data.", context = { "url": cal_link }) from exc
    except httpx.InvalidURL as exc:
        raise exceptions.BadRequest("Invalid calendar URL.", context = { "url": cal_link }) from exc

    try:
        calendar = icalendar.Calendar.from_ical(data)
    except Exception as exc:
        raise exceptions.ServerError("Failed to parse calendar data.") from exc

    for event in calendar.walk('VEVENT'):
        if not event_filter(event):
            calendar.subcomponents.remove(event)
            continue
        if CALENDAR_FILTERS['assignments'](event):
            start_time = event.get('DTSTART')
            if start_time is not None and not event.has_key('DTEND'):
                event['DTSTART'] = event['DTEND'] = icalendar.vDDDTypes(get_due_date(start_time, tz))

    return response.raw(calendar.to_ical(), content_type = 'text/calendar; charset=utf-8')

app.static("/", "./static/", index="index.html")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)