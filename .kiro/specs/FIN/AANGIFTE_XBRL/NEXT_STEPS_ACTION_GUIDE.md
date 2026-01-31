# Next Steps: Action Guide

**Current Status**: Phase 1 Complete ✅  
**Next Phase**: Phase 2 - Obtain Taxonomy  
**Estimated Time**: 1-2 days  
**Last Updated**: January 31, 2026

---

## 🎯 Your Mission

Obtain the official Dutch XBRL taxonomy from Belastingdienst so we can implement the IB Aangifte XBRL submission feature.

---

## 📋 Quick Checklist

### Today (30-60 minutes)

- [ ] **Register as Software Developer**
  - Visit: https://www.belastingdienst.nl/wps/wcm/connect/bldcontenten/belastingdienst/business/tax_return/filing_digital_tax_returns/filing-tax-returns-using-accounting-software/
  - Look for: "Informatie voor softwareontwikkelaars"
  - Complete: Free registration form
  - Receive: Access credentials (may take 1-2 business days)

### This Week (1-2 hours)

- [ ] **Download Taxonomy Package**
  - Option A: https://www.sbr-nl.nl/ (look for "Taxonomie" or "Downloads")
  - Option B: https://www.nltaxonomie.nl/ (search for "Inkomstenbelasting")
  - Option C: Digipoort developer portal (after registration)
  - Download: Latest NT (Nederlandse Taxonomie) version
  - Save: ZIP file to your computer

- [ ] **Extract and Review**
  - Extract: ZIP file contents
  - Create: `backend/templates/xml/taxonomy/` directory
  - Move: Extracted files to taxonomy directory
  - Identify: IB Aangifte entry point schema (e.g., `ib-aangifte-2025.xsd`)

- [ ] **Explore Taxonomy**
  - Visit: https://odb.belastingdienst.nl/
  - Use: Taxonomy Viewer (Yeti) tool
  - Select: Your downloaded taxonomy version
  - Explore: IB Aangifte structure and required fields
  - Document: Key findings

### Next Week (2-3 days)

- [ ] **Update Template**
  - Open: `backend/templates/xml/ib_aangifte_xbrl_template.xml`
  - Replace: Placeholder namespace declarations
  - Update: Field names to match taxonomy
  - Add: All required fields from schema
  - Test: Validate against XSD schema

---

## 🚀 Step-by-Step Instructions

### Step 1: Register (30-60 minutes)

1. **Open your browser** and go to:

   ```
   https://www.belastingdienst.nl/wps/wcm/connect/bldcontenten/belastingdienst/business/tax_return/filing_digital_tax_returns/filing-tax-returns-using-accounting-software/
   ```

2. **Look for** the section titled "Informatie voor softwareontwikkelaars" (Information for software developers)

3. **Click** on the registration link

4. **Fill out** the registration form with:
   - Your name
   - Company name (if applicable)
   - Email address
   - Phone number
   - Brief description of your software project

5. **Submit** the form

6. **Wait** for confirmation email (usually within 1-2 business days)

7. **Save** your access credentials when received

**What you get**:

- Access to Digipoort test environment
- Technical documentation
- Developer support contact
- Early access to taxonomy updates

---

### Step 2: Download Taxonomy (30 minutes)

**Option A: SBR-NL Website** (Recommended)

1. Go to: https://www.sbr-nl.nl/
2. Navigate to "Taxonomie" or "Downloads" section
3. Find the latest **NT (Nederlandse Taxonomie)** version
4. Click download (should be a ZIP file)
5. Save to your Downloads folder

**Option B: NL Taxonomie Website**

1. Go to: https://www.nltaxonomie.nl/
2. Browse or search for "Inkomstenbelasting" (Income Tax)
3. Select the latest version
4. Download the taxonomy package
5. Save to your Downloads folder

**Option C: Digipoort Developer Portal** (After Registration)

1. Log in to your developer account
2. Navigate to "Taxonomie" section
3. Select the taxonomy for your target tax year
4. Download the package
5. Save to your Downloads folder

**What you're downloading**:

- File type: ZIP archive
- Size: Typically 5-20 MB
- Contains: XSD schemas, linkbases, documentation, examples

---

### Step 3: Extract and Organize (15 minutes)

1. **Locate** the downloaded ZIP file in your Downloads folder

2. **Extract** the ZIP file contents

3. **Open** your project in your code editor

4. **Create** a new directory:

   ```
   backend/templates/xml/taxonomy/
   ```

5. **Copy** the extracted files to the taxonomy directory

6. **Verify** the structure looks something like:

   ```
   backend/templates/xml/taxonomy/
   ├── entrypoints/
   │   ├── ib-aangifte-2025.xsd
   │   └── ...
   ├── taxonomies/
   │   ├── bd-inkomstenbelasting.xsd
   │   └── ...
   ├── linkbases/
   │   └── ...
   ├── documentation/
   │   └── ...
   └── examples/
       └── ...
   ```

7. **Document** the taxonomy version and download date in a text file

---

### Step 4: Explore with Yeti (30 minutes)

1. **Open** your browser and go to:

   ```
   https://odb.belastingdienst.nl/
   ```

2. **Find** the "Taxonomy viewer (Yeti)" tool

3. **Select** your downloaded taxonomy version from the dropdown

4. **Navigate** to "Aangifte Inkomstenbelasting" (Income Tax Return)

5. **Explore** the structure:
   - Required fields
   - Optional fields
   - Data types
   - Validation rules

6. **Take notes** on:
   - Field names (e.g., `bd-ib:WinstUitOnderneming`)
   - Required vs optional fields
   - Data types (string, decimal, date, etc.)
   - Any special validation rules

7. **Save** your notes in:
   ```
   backend/templates/xml/taxonomy/FIELD_NOTES.md
   ```

---

### Step 5: Identify Entry Point (15 minutes)

1. **Open** the taxonomy directory in your file explorer

2. **Navigate** to the `entrypoints/` folder

3. **Look for** a file like:
   - `ib-aangifte-2025.xsd`
   - `ib-aangifte-2024.xsd`
   - Or similar (year may vary)

4. **Open** this file in a text editor

5. **Review** the structure:
   - Namespace declarations
   - Required elements
   - Element definitions

6. **Document** the entry point file name and location

---

## 📚 Resources

### Documentation (Read These)

1. **OBTAINING_XBRL_TAXONOMY_GUIDE.md** - Comprehensive guide (start here)
2. **XBRL_TAXONOMY_QUICK_REFERENCE.md** - Quick reference for links and terms
3. **XBRL_IMPLEMENTATION_STATUS.md** - Track overall progress

### Official Websites

- **SBR-NL**: https://www.sbr-nl.nl/
- **NL Taxonomie**: https://www.nltaxonomie.nl/
- **Belastingdienst ODB**: https://odb.belastingdienst.nl/
- **Developer Registration**: https://www.belastingdienst.nl/wps/wcm/connect/bldcontenten/belastingdienst/business/tax_return/filing_digital_tax_returns/filing-tax-returns-using-accounting-software/

---

## ❓ Troubleshooting

### Problem: Can't find registration page

**Solution**:

- The page may be in Dutch
- Look for "softwareontwikkelaars" (software developers)
- Try searching the site for "developer registration"
- Contact Belastingdienst support if needed

### Problem: Can't download taxonomy

**Solution**:

- Try alternative sources (SBR-NL, NL Taxonomie, ODB)
- Check if you need to be logged in
- Verify your internet connection
- Try a different browser

### Problem: Don't understand Dutch documentation

**Solution**:

- Use Google Translate for Dutch pages
- Refer to our English documentation (OBTAINING_XBRL_TAXONOMY_GUIDE.md)
- Key terms are translated in XBRL_TAXONOMY_QUICK_REFERENCE.md
- Focus on the technical files (XSD schemas are in XML, not Dutch)

### Problem: Registration taking too long

**Solution**:

- Wait 1-2 business days for confirmation
- Check your spam folder for confirmation email
- Contact Belastingdienst support if no response after 3 days
- You can still download the taxonomy while waiting

---

## ✅ Success Criteria

You've successfully completed Phase 2 when:

- ✅ Developer registration complete (confirmation received)
- ✅ Taxonomy package downloaded
- ✅ Files extracted and organized in `backend/templates/xml/taxonomy/`
- ✅ IB Aangifte entry point identified
- ✅ Taxonomy structure explored with Yeti
- ✅ Key fields documented

---

## 🎉 After Completion

Once you've completed all the steps above:

1. **Update** the status in `XBRL_IMPLEMENTATION_STATUS.md`
2. **Move to** Phase 3: Update Template
3. **Follow** the instructions in the implementation guide
4. **Test** your updated template against the XSD schema

---

## 📞 Need Help?

### If You're Stuck

1. **Check** the comprehensive guide: `OBTAINING_XBRL_TAXONOMY_GUIDE.md`
2. **Review** the quick reference: `XBRL_TAXONOMY_QUICK_REFERENCE.md`
3. **Contact** Belastingdienst developer support (after registration)
4. **Ask** in SBR-NL community forums

### Common Questions

**Q: How long does registration take?**  
A: Usually 1-2 business days for confirmation.

**Q: Is there a cost?**  
A: No, registration and taxonomy are free.

**Q: Which taxonomy version should I download?**  
A: Download the latest version (NT15 or newer).

**Q: Do I need to know Dutch?**  
A: Helpful but not required. Technical files are in XML/XSD format.

---

## 📅 Timeline

| Task                  | Time      | When      |
| --------------------- | --------- | --------- |
| Register as developer | 30-60 min | Today     |
| Wait for confirmation | 1-2 days  | This week |
| Download taxonomy     | 30 min    | This week |
| Extract and organize  | 15 min    | This week |
| Explore with Yeti     | 30 min    | This week |
| Identify entry point  | 15 min    | This week |

**Total Active Time**: ~2 hours  
**Total Calendar Time**: 1-2 days (including wait time)

---

## 🎯 Your Next Action

**Right now**: Register as software developer

**Link**: https://www.belastingdienst.nl/wps/wcm/connect/bldcontenten/belastingdienst/business/tax_return/filing_digital_tax_returns/filing-tax-returns-using-accounting-software/

**Look for**: "Informatie voor softwareontwikkelaars"

**Time needed**: 30-60 minutes

---

**Good luck! You've got this! 🚀**

---

**Document Status**: Ready for Action  
**Phase**: 2 - Obtain Taxonomy  
**Last Updated**: January 31, 2026
