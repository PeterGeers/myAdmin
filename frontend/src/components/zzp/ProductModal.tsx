/**
 * Product CRUD modal — Formik form with field visibility via useFieldConfig.
 * Follows ui-patterns.md: Cancel (ghost) left, Save (orange) right.
 */

import React, { useState, useEffect } from 'react';
import {
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, Button, FormControl, FormLabel,
  Input, Select, VStack, useToast,
} from '@chakra-ui/react';
import { Formik, Form, Field } from 'formik';
import * as Yup from 'yup';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { Product } from '../../types/zzp';
import { useFieldConfig } from '../../hooks/useFieldConfig';
import { createProduct, updateProduct, getProductTypes } from '../../services/productService';

interface ProductModalProps {
  isOpen: boolean;
  onClose: () => void;
  product: Product | null;
  onSaved: () => void;
}

const VAT_CODES = ['high', 'low', 'zero'];

export const ProductModal: React.FC<ProductModalProps> = ({
  isOpen, onClose, product, onSaved,
}) => {
  const { t } = useTypedTranslation('zzp');
  const toast = useToast();
  const { isVisible, isRequired, loading: configLoading } = useFieldConfig('products');
  const [productTypes, setProductTypes] = useState<string[]>([]);
  const isEdit = !!product;

  useEffect(() => {
    getProductTypes().then(resp => { if (resp.success) setProductTypes(resp.data); });
  }, []);

  const initialValues = {
    product_code: product?.product_code || '',
    name: product?.name || '',
    description: product?.description || '',
    product_type: product?.product_type || 'service',
    unit_price: product?.unit_price ?? 0,
    vat_code: product?.vat_code || 'high',
    unit_of_measure: product?.unit_of_measure || 'uur',
    external_reference: product?.external_reference || '',
  };

  const validationSchema = Yup.object().shape({
    product_code: Yup.string().required('Product code is required'),
    name: Yup.string().required('Name is required'),
    product_type: Yup.string().required('Type is required'),
    vat_code: Yup.string().required('VAT code is required'),
  });

  const handleSubmit = async (values: typeof initialValues, { setSubmitting }: any) => {
    try {
      const resp = isEdit
        ? await updateProduct(product!.id, values as any)
        : await createProduct(values as any);
      if (resp.success) {
        toast({ title: isEdit ? 'Product updated' : 'Product created', status: 'success' });
        onSaved();
      } else {
        toast({ title: resp.error, status: 'error' });
      }
    } catch (err: any) {
      toast({ title: err.message || 'Error', status: 'error' });
    } finally {
      setSubmitting(false);
    }
  };

  const renderField = (name: string, label: string, type = 'text') => {
    if (!isVisible(name)) return null;
    return (
      <FormControl isRequired={isRequired(name)}>
        <FormLabel color="gray.300" fontSize="sm">{label}</FormLabel>
        <Field as={Input} name={name} type={type} size="sm" bg="gray.700"
          color="white" borderColor="gray.600" />
      </FormControl>
    );
  };

  if (configLoading) return null;

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="lg" closeOnOverlayClick={false}>
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white">
        <ModalHeader>{isEdit ? product?.name : t('products.newProduct')}</ModalHeader>
        <ModalCloseButton />
        <Formik initialValues={initialValues} validationSchema={validationSchema}
          onSubmit={handleSubmit} enableReinitialize>
          {({ isSubmitting }) => (
            <Form>
              <ModalBody>
                <VStack spacing={3}>
                  {renderField('product_code', t('products.productCode'))}
                  {renderField('name', t('products.name'))}
                  {renderField('description', t('products.description'))}
                  {isVisible('product_type') && (
                    <FormControl isRequired={isRequired('product_type')}>
                      <FormLabel color="gray.300" fontSize="sm">{t('products.productType')}</FormLabel>
                      <Field as={Select} name="product_type" size="sm" bg="gray.700"
                        color="white" borderColor="gray.600">
                        {productTypes.map(pt => <option key={pt} value={pt}>{pt}</option>)}
                      </Field>
                    </FormControl>
                  )}
                  {renderField('unit_price', t('products.unitPrice'), 'number')}
                  {isVisible('vat_code') && (
                    <FormControl isRequired={isRequired('vat_code')}>
                      <FormLabel color="gray.300" fontSize="sm">{t('products.vatCode')}</FormLabel>
                      <Field as={Select} name="vat_code" size="sm" bg="gray.700"
                        color="white" borderColor="gray.600">
                        {VAT_CODES.map(c => <option key={c} value={c}>{c}</option>)}
                      </Field>
                    </FormControl>
                  )}
                  {renderField('unit_of_measure', t('products.unitOfMeasure'))}
                  {renderField('external_reference', t('products.externalReference'))}
                </VStack>
              </ModalBody>
              <ModalFooter>
                <Button variant="ghost" mr={3} onClick={onClose}>{t('common.cancel')}</Button>
                <Button colorScheme="orange" type="submit" isLoading={isSubmitting}>
                  {t('common.save')}
                </Button>
              </ModalFooter>
            </Form>
          )}
        </Formik>
      </ModalContent>
    </Modal>
  );
};
