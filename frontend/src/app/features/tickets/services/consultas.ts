export const clavesTickets = {
  lista: (hogarId: number, estado: string | undefined) =>
    ['hogar', hogarId, 'tickets', 'lista', estado ?? 'todos'] as const,
  detalle: (hogarId: number, id: number) => ['hogar', hogarId, 'tickets', id] as const,
};
