import api from "../services/api";

export async function sendLeaseContactMessage({ leaseId, channel, subject = "", message }) {
  const payload = { channel, message };
  if (subject) payload.subject = subject;
  const response = await api.post(`/api/leases/${leaseId}/contact-tenant/`, payload);
  return response.data;
}
