export function defaultBudgetPeriodDates(period: string, reference = new Date()) {
  const ref = new Date(reference);
  ref.setHours(12, 0, 0, 0);

  if (period === 'weekly') {
    const day = ref.getDay();
    const mondayOffset = day === 0 ? -6 : 1 - day;
    const start = new Date(ref);
    start.setDate(ref.getDate() + mondayOffset);
    const end = new Date(start);
    end.setDate(start.getDate() + 6);
    return {
      startDate: start.toISOString().split('T')[0],
      endDate: end.toISOString().split('T')[0],
    };
  }

  if (period === 'yearly') {
    const year = ref.getFullYear();
    return {
      startDate: `${year}-01-01`,
      endDate: `${year}-12-31`,
    };
  }

  const year = ref.getFullYear();
  const month = ref.getMonth();
  const startDate = new Date(year, month, 1);
  const endDate = new Date(year, month + 1, 0);
  return {
    startDate: startDate.toISOString().split('T')[0],
    endDate: endDate.toISOString().split('T')[0],
  };
}
