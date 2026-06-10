import {
  Alert,
  AlertIcon,
  Button,
  FormControl,
  FormLabel,
  Grid,
  Input,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalOverlay,
  Textarea,
} from '@chakra-ui/react';
import React from 'react';
import AccountSelect from './common/AccountSelect';
import { AccountOption } from '../hooks/useAccountLookup';
import { Transaction } from './BankingProcessor';

export interface BankingTransactionModalProps {
  isOpen: boolean;
  onClose: () => void;
  editingRecord: Transaction | null;
  setEditingRecord: React.Dispatch<React.SetStateAction<Transaction | null>>;
  isInsertMode: boolean;
  loading: boolean;
  modalError: string;
  chartAccounts: AccountOption[];
  onSave: () => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
  t: (key: string) => string;
}

const BankingTransactionModal: React.FC<BankingTransactionModalProps> = ({
  isOpen,
  onClose,
  editingRecord,
  setEditingRecord,
  isInsertMode,
  loading,
  modalError,
  chartAccounts,
  onSave,
  onKeyDown,
  t,
}) => {
  return (
    <Modal isOpen={isOpen} onClose={onClose} size="xl">
      <ModalOverlay />
      <ModalContent bg="gray.700">
        <ModalHeader color="white">
          {isInsertMode ? t('mutaties.addNewRecord') : `${t('mutaties.editRecord')} - ID: ${editingRecord?.ID}`}
        </ModalHeader>
        <ModalCloseButton color="white" />
        <ModalBody>
          {editingRecord && (
            <Grid templateColumns="repeat(2, 1fr)" gap={4}>
              <FormControl>
                <FormLabel color="white">{t('table.transactionNumber')}</FormLabel>
                <Input value={editingRecord.TransactionNumber || ''} onChange={(e) => setEditingRecord(prev => prev ? { ...prev, TransactionNumber: e.target.value } : prev)} onKeyDown={onKeyDown} bg="gray.600" color="white" />
              </FormControl>
              <FormControl>
                <FormLabel color="white">{t('table.transactionDate')}</FormLabel>
                <Input type="date" value={editingRecord.TransactionDate ? new Date(editingRecord.TransactionDate).toISOString().split('T')[0] : ''} onChange={(e) => setEditingRecord(prev => prev ? { ...prev, TransactionDate: e.target.value } : prev)} onKeyDown={onKeyDown} bg="gray.600" color="white" />
              </FormControl>
              <FormControl gridColumn="span 2">
                <FormLabel color="white">{t('table.description')}</FormLabel>
                <Textarea value={editingRecord.TransactionDescription || ''} onChange={(e) => setEditingRecord(prev => prev ? { ...prev, TransactionDescription: e.target.value } : prev)} bg="gray.600" color="white" />
              </FormControl>
              <FormControl>
                <FormLabel color="white">{t('table.amount')}</FormLabel>
                <Input type="number" step="0.01" value={editingRecord.TransactionAmount || ''} onChange={(e) => setEditingRecord(prev => prev ? { ...prev, TransactionAmount: parseFloat(e.target.value) || 0 } : prev)} onKeyDown={onKeyDown} bg="gray.600" color="white" />
              </FormControl>
              <FormControl>
                <FormLabel color="white">{t('table.administration')}</FormLabel>
                <Input 
                  value={editingRecord.Administration || ''} 
                  isReadOnly 
                  bg="gray.500" 
                  color="gray.300" 
                  cursor="not-allowed"
                  title={t('labels.administrationCannotChange')}
                />
              </FormControl>
              <FormControl>
                <FormLabel color="white">{t('table.debit')}</FormLabel>
                <AccountSelect value={editingRecord.Debet || ''} onChange={(val) => setEditingRecord(prev => prev ? { ...prev, Debet: val } : prev)} accounts={chartAccounts} onKeyDown={onKeyDown} bg="gray.600" color="white" />
              </FormControl>
              <FormControl>
                <FormLabel color="white">{t('table.credit')}</FormLabel>
                <AccountSelect value={editingRecord.Credit || ''} onChange={(val) => setEditingRecord(prev => prev ? { ...prev, Credit: val } : prev)} accounts={chartAccounts} onKeyDown={onKeyDown} bg="gray.600" color="white" />
              </FormControl>
              <FormControl>
                <FormLabel color="white">{t('table.referenceNumber')}</FormLabel>
                <Input value={editingRecord.ReferenceNumber || ''} onChange={(e) => setEditingRecord(prev => prev ? { ...prev, ReferenceNumber: e.target.value } : prev)} onKeyDown={onKeyDown} bg="gray.600" color="white" />
              </FormControl>
              <FormControl>
                <FormLabel color="white">{t('table.ref1')}</FormLabel>
                <Input value={editingRecord.Ref1 || ''} onChange={(e) => setEditingRecord(prev => prev ? { ...prev, Ref1: e.target.value } : prev)} onKeyDown={onKeyDown} bg="gray.600" color="white" />
              </FormControl>
              <FormControl>
                <FormLabel color="white">{t('table.ref2')}</FormLabel>
                <Input value={editingRecord.Ref2 || ''} onChange={(e) => setEditingRecord(prev => prev ? { ...prev, Ref2: e.target.value } : prev)} onKeyDown={onKeyDown} bg="gray.600" color="white" />
              </FormControl>
              <FormControl gridColumn="span 2">
                <FormLabel color="white">{t('table.ref3')}</FormLabel>
                <Textarea value={editingRecord.Ref3 || ''} onChange={(e) => setEditingRecord(prev => prev ? { ...prev, Ref3: e.target.value } : prev)} bg="gray.600" color="white" />
              </FormControl>
              <FormControl>
                <FormLabel color="white">{t('table.ref4')}</FormLabel>
                <Input value={editingRecord.Ref4 || ''} onChange={(e) => setEditingRecord(prev => prev ? { ...prev, Ref4: e.target.value } : prev)} onKeyDown={onKeyDown} bg="gray.600" color="white" />
              </FormControl>
            </Grid>
          )}
        </ModalBody>
        <ModalFooter>
          {modalError && (
            <Alert status="error" mb={3} mr="auto" borderRadius="md" flex="1" bg="red.100" color="red.900" borderWidth="1px" borderColor="red.300">
              <AlertIcon color="red.600" />
              {modalError}
            </Alert>
          )}
          <Button colorScheme="gray" mr={3} onClick={onClose}>{t('labels.cancel')}</Button>
          <Button colorScheme="orange" onClick={onSave} isLoading={loading}>
            {isInsertMode ? t('mutaties.insertRecord') : t('mutaties.updateRecord')}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

export default BankingTransactionModal;
