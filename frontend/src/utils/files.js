import api from "../services/api";

export const getFilenameFromDisposition = (value) => {
  if (!value) return null;
  const utf8Match = value.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1]);
  }
  const plainMatch = value.match(/filename="?([^";]+)"?/i);
  return plainMatch?.[1] || null;
};

export async function fetchBlobFile(url, fallbackName = "download.bin") {
  const response = await api.get(url, { responseType: "blob" });
  const contentDisposition = response.headers?.["content-disposition"];
  const filename = getFilenameFromDisposition(contentDisposition) || fallbackName;
  return {
    blob: response.data,
    filename,
    contentType: response.headers?.["content-type"] || response.data?.type || "",
  };
}

export async function downloadBlob(url, fallbackName = "download.bin") {
  const { blob, filename } = await fetchBlobFile(url, fallbackName);
  const blobUrl = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(blobUrl);
}

export function downloadCsv(filename, headers, rows) {
  const csv = [
    headers.join(","),
    ...rows.map((row) =>
      row.map((cell) => `"${String(cell ?? "").replaceAll('"', '""')}"`).join(",")
    ),
  ].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
