export function getErrorMessage(error, fallback = "Something went wrong.") {
  if (!error) return fallback;
  if (error.code === "ERR_NETWORK" || !error.response) {
    return "Network error. Please check your connection.";
  }

  const detail = error.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  const values = Object.values(error.response?.data || {});
  const first = values.find((value) => typeof value === "string" && value.trim());
  if (first) {
    return first;
  }

  const firstArrayValue = values.find((value) => Array.isArray(value) && value.length);
  if (firstArrayValue?.[0]) {
    return String(firstArrayValue[0]);
  }

  return fallback;
}
