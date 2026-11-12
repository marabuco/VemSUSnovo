export type UnitType =
  | 'USF'
  | 'UBS'
  | 'Centro de Saúde'
  | 'Policlínica'
  | 'CAPS'
  | 'UPA'
  | 'SAMU'
  | 'Maternidade'
  | 'Hospital'
  | 'Centro Especializado';

export type ServiceTag =
  | 'Vacinação'
  | 'Urgência'
  | 'Atenção Básica'
  | 'Saúde Mental'
  | 'Saúde Bucal'
  | 'Saúde da Criança'
  | 'Saúde da Mulher'
  | 'Saúde do Idoso'
  | 'Farmácia'
  | 'Exames'
  | 'Curativos'
  | 'Pré-natal'
  | 'Planejamento Familiar'
  | 'Doenças Crônicas'
  | 'Reabilitação'
  | 'Especialidades'
  | 'Puericultura'
  | 'Hipertensão e Diabetes';

export interface HealthUnit {
  id: string;
  name: string;
  type: UnitType;
  address: string;
  neighborhood: string;
  phone?: string;
  schedule?: string;
  lat: number;
  lng: number;
  services: ServiceTag[];
  beforeVisit?: string;
  status: 'active' | 'unknown';
  cnes?: string;
  geoSource?: 'official' | 'geocoded'; // 'geocoded' = posição aproximada (avisar o usuário)
  distanceKm?: number; // calculado pelo servidor quando a localização é enviada
  dataSource: 'official' | 'mock';
}

export interface AppState {
  searchTerm: string;
  selectedServices: ServiceTag[];
  selectedUnitType: UnitType | '';
  childMode: boolean;
  userLocation: { lat: number; lng: number } | null;
  units: HealthUnit[];
  filteredUnits: HealthUnit[];
  selectedUnit: HealthUnit | null;
  theme: 'light' | 'dark';
  view: 'home' | 'results' | 'unit' | 'samu' | 'about' | 'privacy';
  loading: boolean;
  error: string | null;
  mockMode: boolean;
  accessibilitySettings: {
    fontSize: 'normal' | 'large' | 'xlarge';
    highContrast: boolean;
    simplifiedUI: boolean;
    reducedMotion: boolean;
  };
}

export type AppAction =
  | { type: 'SET_SEARCH'; payload: string }
  | { type: 'SET_SERVICES'; payload: ServiceTag[] }
  | { type: 'TOGGLE_SERVICE'; payload: ServiceTag }
  | { type: 'SET_UNIT_TYPE'; payload: UnitType | '' }
  | { type: 'SET_CHILD_MODE'; payload: boolean }
  | { type: 'SET_LOCATION'; payload: { lat: number; lng: number } | null }
  | { type: 'SET_UNITS'; payload: HealthUnit[] }
  | { type: 'SET_FILTERED'; payload: HealthUnit[] }
  | { type: 'SELECT_UNIT'; payload: HealthUnit | null }
  | { type: 'SET_THEME'; payload: 'light' | 'dark' }
  | { type: 'SET_VIEW'; payload: AppState['view'] }
  | { type: 'SET_LOADING'; payload: boolean }
  | { type: 'SET_ERROR'; payload: string | null }
  | { type: 'SET_MOCK_MODE'; payload: boolean }
  | { type: 'SET_ACCESSIBILITY'; payload: Partial<AppState['accessibilitySettings']> }
  | { type: 'SEARCH' };
