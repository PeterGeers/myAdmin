export interface ParamOption {
  value: string;
  label: string;
}

export interface ParamDef {
  label: string;
  label_nl?: string;
  type: 'string' | 'number' | 'boolean' | 'json';
  required?: boolean;
  default?: any;
  options?: ParamOption[];
  visible_when?: Record<string, string>;
  description?: string;
  read_only?: boolean;
  min?: number;
  max?: number;
  current_value?: any;
  missing?: boolean;
}

export interface SchemaSection {
  label: string;
  label_nl?: string;
  module?: string;
  params: Record<string, ParamDef>;
}

export interface ParameterSchemaResponse {
  success: boolean;
  tenant: string;
  active_modules: string[];
  schema: Record<string, SchemaSection>;
}
