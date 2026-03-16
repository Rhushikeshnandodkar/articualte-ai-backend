from datetime import timedelta

from django.utils import timezone

from .models import Conversation


def _distinct_practice_dates(user):
  """
  Return a sorted list of unique dates (date objects) on which the user
  completed at least one conversation.
  """
  qs = (
    Conversation.objects.filter(
      user=user,
      status=Conversation.STATUS_ENDED,
      ended_at__isnull=False,
    )
    .order_by("ended_at")
    .values_list("ended_at", flat=True)
  )
  dates = []
  for dt in qs:
    if dt is None:
      continue
    # Use local date so streaks follow the user's timezone setting on server
    d = timezone.localtime(dt).date()
    if not dates or dates[-1] != d:
      dates.append(d)
  return dates


def compute_streak_data(user):
  """
  Compute streak information for the given user based on conversation history.

  Returns a dict with:
  - current_streak: int
  - longest_streak: int
  - total_practice_days: int
  - streak_broken: bool (True if there was a gap of at least one full day)
  - last_active_date: iso string or None
  - segments: recent streak segments (start/end/length as iso strings)
  """
  dates = _distinct_practice_dates(user)
  total_days = len(dates)
  if not dates:
    return {
      "current_streak": 0,
      "longest_streak": 0,
      "total_practice_days": 0,
      "streak_broken": False,
      "last_active_date": None,
      "segments": [],
    }

  segments = []
  longest_streak = 0

  run_start = dates[0]
  run_prev = dates[0]

  for d in dates[1:]:
    if d == run_prev + timedelta(days=1):
      # continues streak
      run_prev = d
    elif d == run_prev:
      # same calendar day, already included
      continue
    else:
      length = (run_prev - run_start).days + 1
      longest_streak = max(longest_streak, length)
      segments.append((run_start, run_prev, length))
      run_start = run_prev = d

  # final segment
  final_length = (run_prev - run_start).days + 1
  longest_streak = max(longest_streak, final_length)
  segments.append((run_start, run_prev, final_length))

  today = timezone.localdate()
  last_date = dates[-1]

  # Current streak is the last segment only if it ends today or yesterday.
  last_seg_start, last_seg_end, last_seg_len = segments[-1]
  if last_seg_end in (today, today - timedelta(days=1)):
    current_streak = last_seg_len
  else:
    current_streak = 0

  # Streak is considered broken if last active day is more than 1 day ago.
  streak_broken = last_date < today - timedelta(days=1)

  # Convert segments to a serializable, recent-only form (e.g. last 10 segments).
  serialized_segments = [
    {
      "start_date": s.isoformat(),
      "end_date": e.isoformat(),
      "length": length,
    }
    for s, e, length in segments[-10:]
  ]

  return {
    "current_streak": current_streak,
    "longest_streak": longest_streak,
    "total_practice_days": total_days,
    "streak_broken": streak_broken,
    "last_active_date": last_date.isoformat(),
    "segments": serialized_segments,
  }


def compute_and_update_profile_streaks(profile):
  """
  Compute streaks for the profile's user and persist summary numbers on the profile.
  Returns the full streak data dict (including segments) for convenience.
  """
  if not profile or not profile.user:
    return {
      "current_streak": 0,
      "longest_streak": 0,
      "total_practice_days": 0,
      "streak_broken": False,
      "last_active_date": None,
      "segments": [],
    }

  data = compute_streak_data(profile.user)
  profile.current_streak = data["current_streak"]
  profile.longest_streak = data["longest_streak"]
  profile.total_practice_days = data["total_practice_days"]
  profile.save(
    update_fields=["current_streak", "longest_streak", "total_practice_days", "updated_at"]
  )
  return data

