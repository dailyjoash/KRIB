export function getErrorMessage(error, fallback = "Something went wrong.") {
  if (!error) return fallback;
  const message = String(error?.message || "").toLowerCase();

  if (error.code === "ECONNABORTED" || message.includes("timeout")) {
    return "The server may be waking up. Please wait a moment and try again.";
  }

  if (error.code === "ERR_NETWORK" || !error.response) {
    return "Unable to reach the server right now. If this is the first request, please wait a moment and try again.";
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
