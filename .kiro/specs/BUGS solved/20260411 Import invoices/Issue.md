AFter the implementation of check accounts exists see:.kiro\specs\FIN\DebetCredit validation
When i Import an invoice with ZERO Vat i get the error message VAT account 2010 does not exists. But this account exists always and is used to store VAT amounts
This error is probably due to the fact the VAT amount is ZERO which results that the second transaction will not be saved.