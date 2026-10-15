export interface ParamOption {
  value: string;
  label: string;
}

/**
 * A parameter value as delivered by the backend schema. The concrete shape
 * depends on `type` ('string' | 'number' | 'boolean' | 'json'); `json`
 * carries an arbitrary serialized shape. Consumers narrow/coerce at the point
 * of use (e.g. `String(current_value)`), so this stays intentionally dynamic
 * as `unknown` rather than `any` — forcing a cast at the boundary instead of
 * silently allowing unchecked member access.
 */
export type ParamValue = unknown;

export interface ParamDef {
  label: string;
  label_nl?: string;
  type: 'string' | 'number' | 'boolean' | 'json';
  required?: boolean;
  default?: ParamValue;
  options?: ParamOption[];
  visible_when?: Record<string, string>;
  description?: string;
  read_only?: boolean;
  min?: number;
  max?: number;
  current_value?: ParamValue;
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
