import React, { useState, useEffect } from 'react';
import {
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, Button, FormControl, FormLabel,
  Input, Select, Textarea, VStack, HStack, useToast
} from '@chakra-ui/react';
import { listAccounts } from '../../services/chartOfAccountsService';
import { createAsset, updateAsset } from '../../services/assetService';

interface AccountOption {
  Account: string;
  AccountName: string;
  parameters?: string;
}

interface AssetFormProps {
  isOpen: boolean;
  onClose: () => void;
  onSaved: () => void;
  mode: 'create' | 'edit';
  asset?: Record<string, unknown> | null;
}

export default function AssetForm({ isOpen, onClose, onSaved, mode, asset }: AssetFormProps) {
  const [form, setForm] = useState({
    description: '', category: '', ledger_account: '',
    depreciation_account: '', purchase_date: '', purchase_amount: '',
    depreciation_method: 'straight_line', depreciation_frequency: 'annual',
    depreciation_rate: '',
    useful_life_years: '', residual_value: '0',
    reference_number: '', notes: '',
  });
  const [assetAccounts, setAssetAccounts] = useState<AccountOption[]>([]);
  const [allAccounts, setAllAccounts] = useState<AccountOption[]>([]);
  const [saving, setSaving] = useState(false);
  const toast = useToast();

  useEffect(() => {
    if (!isOpen) return;
    // Load accounts
    listAccounts({ limit: 500 }).then(res => {
      const accs = (res.accounts || []) as AccountOption[];
      setAllAccounts(accs);
      // Filter by asset_account parameter
      const assetAccs = accs.filter(a => {
        try {
          const params = a.parameters ? JSON.parse(a.parameters) : {};
          return params.asset_account === true;
        } catch { return false; }
      });
      setAssetAccounts(assetAccs);
    }).catch(() => {});

    // Populate form for edit mode
    if (mode === 'edit' && asset) {
      setForm({
        description: (asset.description as string) || '',
        category: (asset.category as string) || '',
        ledger_account: (asset.ledger_account as string) || '',
        depreciation_account: (asset.depreciation_account as string) || '',
        purchase_date: (asset.purchase_date as string) || '',
        purchase_amount: String(asset.purchase_amount || ''),
        depreciation_method: (asset.depreciation_method as string) || 'straight_line',
        depreciation_frequency: (asset.depreciation_frequency as string) || 'annual',
        depreciation_rate: String(asset.depreciation_rate || ''),
        useful_life_years: String(asset.useful_life_years || ''),
        residual_value: String(asset.residual_value || '0'),
        reference_number: (asset.reference_number as string) || '',
        notes: (asset.notes as string) || '',
      });
    } else {
      setForm({
        description: '', category: '', ledger_account: '',
        depreciation_account: '', purchase_date: '', purchase_amount: '',
        depreciation_method: 'straight_line', depreciation_frequency: 'annual',
        depreciation_rate: '',
        useful_life_years: '', residual_value: '0',
        reference_number: '', notes: '',
      });
    }
  }, [isOpen, mode, asset]);

  const handleSave = async () => {
    if (!form.description || !form.ledger_account || !form.purchase_date || !form.purchase_amount) {
      toast({ title: 'Please fill required fields', status: 'warning', duration: 3000 });
      return;
    }
    setSaving(true);
    try {
      const data: Record<string, unknown> = {
        ...form,
        purchase_amount: parseFloat(form.purchase_amount),
        residual_value: parseFloat(form.residual_value || '0'),
        depreciation_rate: form.depreciation_rate ? parseFloat(form.depreciation_rate) : null,
        useful_life_years: form.useful_life_years ? parseInt(form.useful_life_years) : null,
      };
      if (mode === 'create') {
        await createAsset(data);
        toast({ title: 'Asset created', status: 'success', duration: 3000 });
      } else if (asset) {
        await updateAsset(asset.id as number, data);
        toast({ title: 'Asset updated', status: 'success', duration: 3000 });
      }
      onSaved();
      onClose();
    } catch (error) {
      toast({
        title: 'Error saving asset',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error', duration: 5000,
      });
    } finally {
      setSaving(false);
    }
  };

  const set = (field: string, value: string) => setForm(prev => ({ ...prev, [field]: value }));
  const opt = { bg: 'gray.600', color: 'white', borderColor: 'gray.500' };
  const selStyle = { background: '#2D3748' };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="xl">
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white">
        <ModalHeader color="orange.400">
          {mode === 'create' ? 'New Asset' : 'Edit Asset'}
        </ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          <VStack spacing={3}>
            <FormControl isRequired>
              <FormLabel color="gray.300">Description</FormLabel>
              <Input value={form.description} onChange={e => set('description', e.target.value)}
                placeholder="e.g., Toyota Yaris 2024" {...opt} />
            </FormControl>

            <HStack w="100%" spacing={3}>
              <FormControl>
                <FormLabel color="gray.300">Category</FormLabel>
                <Select value={form.category} onChange={e => set('category', e.target.value)}
                  placeholder="Select..." {...opt}>
                  {['vehicle','real_estate','equipment','financial','IT'].map(c =>
                    <option key={c} value={c} style={selStyle}>{c}</option>)}
                </Select>
              </FormControl>
              <FormControl isRequired>
                <FormLabel color="gray.300">Asset Account</FormLabel>
                <Select value={form.ledger_account} onChange={e => set('ledger_account', e.target.value)}
                  placeholder="Select..." {...opt}>
                  {assetAccounts.map(a =>
                    <option key={a.Account} value={a.Account} style={selStyle}>
                      {a.Account} — {a.AccountName}
                    </option>)}
                </Select>
              </FormControl>
            </HStack>

            <HStack w="100%" spacing={3}>
              <FormControl isRequired>
                <FormLabel color="gray.300">Purchase Date</FormLabel>
                <Input type="date" value={form.purchase_date}
                  onChange={e => set('purchase_date', e.target.value)} {...opt} />
              </FormControl>
              <FormControl isRequired>
                <FormLabel color="gray.300">Purchase Amount (€)</FormLabel>
                <Input type="number" step="0.01" value={form.purchase_amount}
                  onChange={e => set('purchase_amount', e.target.value)} {...opt} />
              </FormControl>
            </HStack>

            <HStack w="100%" spacing={3}>
              <FormControl>
                <FormLabel color="gray.300">Depreciation Method</FormLabel>
                <Select value={form.depreciation_method}
                  onChange={e => set('depreciation_method', e.target.value)} {...opt}>
                  <option value="straight_line" style={selStyle}>Straight Line</option>
                  <option value="declining_balance" style={selStyle}>Declining Balance</option>
                  <option value="none" style={selStyle}>No Depreciation</option>
                </Select>
              </FormControl>
              <FormControl>
                <FormLabel color="gray.300">Frequency</FormLabel>
                <Select value={form.depreciation_frequency}
                  onChange={e => set('depreciation_frequency', e.target.value)} {...opt}>
                  <option value="annual" style={selStyle}>Annual</option>
                  <option value="quarterly" style={selStyle}>Quarterly</option>
                  <option value="monthly" style={selStyle}>Monthly</option>
                </Select>
              </FormControl>
            </HStack>

            {form.depreciation_method === 'declining_balance' && (
              <FormControl>
                <FormLabel color="gray.300">Depreciation Rate (%)</FormLabel>
                <Input type="number" step="0.01" value={form.depreciation_rate}
                  onChange={e => set('depreciation_rate', e.target.value)}
                  placeholder="e.g., 40" {...opt} />
              </FormControl>
            )}

            <HStack w="100%" spacing={3}>
              <FormControl>
                <FormLabel color="gray.300">Useful Life (years)</FormLabel>
                <Input type="number" value={form.useful_life_years}
                  onChange={e => set('useful_life_years', e.target.value)} {...opt} />
              </FormControl>
              <FormControl>
                <FormLabel color="gray.300">Residual Value (€)</FormLabel>
                <Input type="number" step="0.01" value={form.residual_value}
                  onChange={e => set('residual_value', e.target.value)} {...opt} />
              </FormControl>
            </HStack>

            <HStack w="100%" spacing={3}>
              <FormControl>
                <FormLabel color="gray.300">Depreciation Account</FormLabel>
                <Select value={form.depreciation_account}
                  onChange={e => set('depreciation_account', e.target.value)}
                  placeholder="Select..." {...opt}>
                  {allAccounts.filter(a => a.Account.startsWith('4')).map(a =>
                    <option key={a.Account} value={a.Account} style={selStyle}>
                      {a.Account} — {a.AccountName}
                    </option>)}
                </Select>
              </FormControl>
            </HStack>

            <FormControl>
              <FormLabel color="gray.300">Invoice Reference</FormLabel>
              <Input value={form.reference_number}
                onChange={e => set('reference_number', e.target.value)}
                placeholder="e.g., INV-2024-0042" {...opt} />
            </FormControl>

            <FormControl>
              <FormLabel color="gray.300">Notes</FormLabel>
              <Textarea value={form.notes} onChange={e => set('notes', e.target.value)}
                placeholder="Optional notes..." {...opt} rows={2} />
            </FormControl>
          </VStack>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" mr={3} onClick={onClose}>Cancel</Button>
          <Button colorScheme="orange" onClick={handleSave} isLoading={saving} isDisabled={saving}>
            {mode === 'create' ? 'Create' : 'Save'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
