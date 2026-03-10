export const formatKES = (value) => {
  const amount = Number(value ?? 0);
  return `Ksh ${amount.toLocaleString("en-KE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
};
