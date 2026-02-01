export type ExchangeName = "hyperliquid" | "binance" | "okx" | (string & {});

export type ExchangeCredentialStatus = {
  api_key: boolean;
  api_secret: boolean;
  passphrase: boolean;
  agent_key: boolean;
};

export type ExchangeValidationStatus = {
  status: "unvalidated" | "valid" | "invalid" | (string & {});
  last_validated_at?: string | null;
  error?: string | null;
};

export type ExchangeAccount = {
  id: string;
  exchange: ExchangeName;
  name: string;
  wallet_address?: string | null;
  is_active: boolean;
  is_testnet: boolean;
  credentials: ExchangeCredentialStatus;
  validation: ExchangeValidationStatus;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ExchangeCredentialsPayload = {
  api_key: string;
  api_secret: string;
  passphrase?: string;
  agent_key?: string;
};

export type ExchangeCreatePayload = {
  exchange: ExchangeName;
  name: string;
  is_testnet: boolean;
  wallet_address?: string;
  credentials: ExchangeCredentialsPayload;
};
