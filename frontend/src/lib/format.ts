/**
 * The API returns UTC timestamps without a timezone designator (SQLite drops it),
 * so a bare `new Date(value)` would be read as local time. Assume UTC when absent.
 */
export function formatTimestamp(value: string): string {
  const hasTimezone = /(Z|[+-]\d{2}:?\d{2})$/i.test(value);
  const timestamp = new Date(hasTimezone ? value : `${value}Z`);

  if (Number.isNaN(timestamp.getTime())) {
    return value;
  }

  return timestamp.toLocaleString();
}
