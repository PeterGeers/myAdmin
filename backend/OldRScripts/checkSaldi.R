## Functions that shows the actual values of current banking accounts
source("myFunctions.r")
getPackages(c("plyr", "dplyr", "stringr", "config", "DBI"))

##config <- config::get(config = 'test', file = "./conf/config.yml")
config <- config::get(config = 'production', file = "conf/config.yml")

## read accounts to validate saldi Note Account within Administration must be unique
accounts <- getSQLtable("lookupbankaccounts_r")

## read vw_mutaties
df <- getSQLtable("vw_mutaties")
dfMutaties <- getSQLtable("mutaties")


## Only relevant administrations
pattern <- paste0(unique(accounts$Administration), sep="|", collapse ="")
pattern <- substr(pattern,1, nchar(pattern)-1)
df1 <- subset(df, grepl(pattern, df$Administration))

## Only relevant reknums
pattern <- paste0(unique(accounts$Account), sep="|", collapse ="")
pattern <- substr(pattern,1, nchar(pattern)-1)
df1 <- subset(df1, grepl(pattern, df1$Reknum))

### Define saldo by relevant ledger account
saldo <- df1 %>% 
    group_by(Reknum, Administration) %>% 
    reframe(amount = round(sum(Amount),2), .groups="drop")

saldo$description <- ""  ## add column for last description

##### Now find the last record in df1 for each row in saldo (last(df1$TransactionDescription,1))
##### Here we have to read mutaties in stead of vw_mutaties
for (i in 1:nrow(saldo))
{
       df2 <- subset(dfMutaties, grepl(saldo$Administration[i], dfMutaties$Administration))
       df2 <- subset(df2, grepl(saldo$Reknum[i], df2$Debet)|grepl(saldo$Reknum[i], df2$Credit))
       df2 <- subset(df2, grepl(max(df2$TransactionDate), df2$TransactionDate))  ### Select rows of last TransactionDate
       df2 <- arrange(df2, df2$Ref2)                           #### Arrange on transaction sequence number retrieved from RABO
       saldo$description[i]<- last(df2$TransactionDescription) ### The amount mentioned must be the same as calculated
       
}

## view(saldo)
