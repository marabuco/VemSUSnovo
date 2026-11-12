import type { HealthUnit, ServiceTag, UnitType } from '../types';
import { MOCK_UNITS, SERVICE_MAP } from '../data/mock';

/**
 * O frontend NÃO fala mais com dados.recife.pe.gov.br e NÃO tem token.
 * Quem consulta a Prefeitura é o backend Python (/api); aqui só consumimos o nosso próprio /api.
 */
const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '';
// Dados fictícios só existem se você pedir explicitamente (VITE_ALLOW_MOCK=true) — nunca em produção.
const ALLOW_MOCK = import.meta.env.VITE_ALLOW_MOCK === 'true';

export const NO_ADDRESS = 'Informação não disponível na base oficial.';

export class ApiError extends Error {}

type Coords = { lat: number; lng: number } | null;

export interface UnitQuery {
  q?: string;
  services?: ServiceTag[];
  type?: UnitType | '';
  child?: boolean;
  location?: Coords;
  limit?: number;
}

async function getJson<T>(path: string, params?: URLSearchParams, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}${params ? `?${params}` : ''}`, { signal });
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e;
    throw new ApiError('Não foi possível conectar ao servidor. Verifique sua internet e tente novamente.');
  }
  if (res.status === 429) throw new ApiError('Muitas buscas seguidas. Aguarde alguns segundos e tente de novo.');
  if (!res.ok) throw new ApiError('O serviço está temporariamente indisponível. Tente novamente em instantes.');
  return res.json() as Promise<T>;
}

/** Busca no servidor (ranking e distância calculados lá). Preferir esta função nas telas. */
export async function searchUnits(query: UnitQuery, signal?: AbortSignal): Promise<{ total: number; units: HealthUnit[] }> {
  const p = new URLSearchParams();
  if (query.q?.trim()) p.set('q', query.q.trim());
  query.services?.forEach(s => p.append('services', s));
  if (query.type) p.set('type', query.type);
  if (query.child) p.set('child', 'true');
  if (query.location) {
    p.set('lat', String(query.location.lat));
    p.set('lng', String(query.location.lng));
  }
  if (query.limit) p.set('limit', String(query.limit));
  return getJson('/api/units', p, signal);
}

/** Carrega todas as unidades georreferenciadas (mantém a assinatura antiga usada pelo app). */
export async function fetchUnits(): Promise<{ units: HealthUnit[]; isMock: boolean }> {
  try {
    const { units } = await searchUnits({ limit: 1000 });
    if (units.length === 0) throw new ApiError('Os dados das unidades ainda estão sendo carregados. Tente novamente em instantes.');
    return { units, isMock: false };
  } catch (e) {
    if (ALLOW_MOCK) return { units: MOCK_UNITS, isMock: true };
    throw e; // a tela mostra o erro; nunca exibimos endereços fictícios como se fossem reais
  }
}

export interface DataMeta {
  source: string;
  dataset: string;
  datasetUrl: string;
  license: string;
  unitsServed: number;
  unitsWithoutLocation: number;
  approximateLocation: number;
  lastSync: string | null;
}
export const fetchMeta = () => getJson<DataMeta>('/api/meta');

// ---------------------------------------------------------------------------------------------
// Utilitários mantidos por compatibilidade (modo local/offline). Bugs do protótipo corrigidos.
// ---------------------------------------------------------------------------------------------
const fold = (s: string) => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
const STOP = new Set(['de', 'da', 'do', 'das', 'dos', 'e', 'em', 'na', 'no', 'para', 'por', 'um', 'uma', 'com', 'perto']);

const SYNONYMS: Record<string, string[]> = Object.fromEntries(
  Object.entries(SERVICE_MAP).map(([k, v]) => [fold(k), v as string[]]),
);

function terms(query: string) {
  const phrase = fold(query);
  const words = phrase.split(/\s+/).filter(w => w.length >= 2 && !STOP.has(w));
  const wanted = new Set<string>(SYNONYMS[phrase] ?? []);
  words.forEach(w => (SYNONYMS[w] ?? []).forEach(s => wanted.add(s)));
  return { phrase, words, wanted };
}

export function scoreUnit(unit: HealthUnit, searchTerm: string, userLocation: Coords): number {
  const { phrase, words, wanted } = terms(searchTerm);
  let score = 0;

  if (phrase) {
    // Correção: com termo vazio o protótipo fazia includes('') === true e dava +30 a todas as unidades.
    const svc = unit.services.map(fold);
    if (unit.services.some(s => wanted.has(s)) || svc.includes(phrase)) score += 50;
    else if (words.some(w => svc.some(s => s.includes(w)))) score += 30;
    const name = fold(unit.name);
    if (name.includes(phrase) || words.some(w => name.includes(w))) score += 20;
  }
  if (unit.schedule) score += 10;
  if (unit.phone) score += 5;
  if (unit.address !== NO_ADDRESS) score += 10;

  if (userLocation) {
    const dist = haversine(userLocation.lat, userLocation.lng, unit.lat, unit.lng);
    if (dist < 2) score += 20;
    else if (dist < 5) score += 10;
  }
  return score;
}

export function haversine(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

const CHILD_SERVICES: ServiceTag[] = ['Saúde da Criança', 'Vacinação', 'Puericultura', 'Saúde Bucal'];

export function filterAndSort(
  units: HealthUnit[],
  searchTerm: string,
  selectedServices: ServiceTag[],
  selectedUnitType: UnitType | '',
  childMode: boolean,
  userLocation: Coords,
): HealthUnit[] {
  const { phrase, words, wanted } = terms(searchTerm);
  let list = units;
  if (childMode) list = list.filter(u => u.services.some(s => CHILD_SERVICES.includes(s)));
  if (selectedUnitType) list = list.filter(u => u.type === selectedUnitType);
  if (selectedServices.length) list = list.filter(u => selectedServices.every(s => u.services.includes(s)));
  if (phrase) {
    list = list.filter(u => {
      const hay = fold([u.name, u.neighborhood, u.address, ...u.services].join(' '));
      return hay.includes(phrase) || u.services.some(s => wanted.has(s)) || words.some(w => hay.includes(w));
    });
  }
  // Correção: calcula o score uma única vez por unidade (antes era recalculado a cada comparação do sort).
  return list
    .map(u => ({ u, s: scoreUnit(u, searchTerm, userLocation) }))
    .sort((a, b) => b.s - a.s || a.u.name.localeCompare(b.u.name, 'pt-BR'))
    .map(x => x.u);
}
