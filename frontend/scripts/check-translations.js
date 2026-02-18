#!/usr/bin/env node

/**
 * Translation Completeness Checker
 * 
 * Checks that all translation keys exist in both Dutch (nl) and English (en) languages.
 * Reports missing keys, extra keys, and provides statistics.
 */

const fs = require('fs');
const path = require('path');

// Colors for console output
const colors = {
  reset: '\x1b[0m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m',
};

// Translation file paths
const LOCALES_DIR = path.join(__dirname, '..', 'src', 'locales');
const LANGUAGES = ['nl', 'en'];
const NAMESPACES = ['common', 'auth', 'reports', 'str', 'banking', 'admin', 'errors', 'validation'];

/**
 * Load JSON file
 */
function loadJSON(filePath) {
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    return JSON.parse(content);
  } catch (error) {
    console.error(`${colors.red}Error loading ${filePath}: ${error.message}${colors.reset}`);
    return null;
  }
}

/**
 * Get all keys from nested object
 */
function getAllKeys(obj, prefix = '') {
  const keys = [];
  
  for (const key in obj) {
    const fullKey = prefix ? `${prefix}.${key}` : key;
    
    if (typeof obj[key] === 'object' && obj[key] !== null && !Array.isArray(obj[key])) {
      keys.push(...getAllKeys(obj[key], fullKey));
    } else {
      keys.push(fullKey);
    }
  }
  
  return keys;
}

/**
 * Compare two sets of keys
 */
function compareKeys(keys1, keys2) {
  const set1 = new Set(keys1);
  const set2 = new Set(keys2);
  
  const missing = keys1.filter(key => !set2.has(key));
  const extra = keys2.filter(key => !set1.has(key));
  
  return { missing, extra };
}

/**
 * Check translations for a namespace
 */
function checkNamespace(namespace) {
  console.log(`\n${colors.cyan}Checking namespace: ${namespace}${colors.reset}`);
  console.log('='.repeat(60));
  
  const translations = {};
  let hasErrors = false;
  
  // Load translations for all languages
  for (const lang of LANGUAGES) {
    const filePath = path.join(LOCALES_DIR, lang, `${namespace}.json`);
    
    if (!fs.existsSync(filePath)) {
      console.log(`${colors.red}✗ Missing file: ${filePath}${colors.reset}`);
      hasErrors = true;
      continue;
    }
    
    translations[lang] = loadJSON(filePath);
    
    if (!translations[lang]) {
      hasErrors = true;
      continue;
    }
  }
  
  // If any language is missing, skip comparison
  if (Object.keys(translations).length !== LANGUAGES.length) {
    return { hasErrors: true, stats: null };
  }
  
  // Get all keys for each language
  const keys = {};
  for (const lang of LANGUAGES) {
    keys[lang] = getAllKeys(translations[lang]);
  }
  
  // Compare Dutch (reference) with English
  const { missing, extra } = compareKeys(keys.nl, keys.en);
  
  // Report results
  if (missing.length === 0 && extra.length === 0) {
    console.log(`${colors.green}✓ All keys match! (${keys.nl.length} keys)${colors.reset}`);
  } else {
    hasErrors = true;
    
    if (missing.length > 0) {
      console.log(`\n${colors.red}Missing in English (${missing.length}):${colors.reset}`);
      missing.forEach(key => console.log(`  - ${key}`));
    }
    
    if (extra.length > 0) {
      console.log(`\n${colors.yellow}Extra in English (${extra.length}):${colors.reset}`);
      extra.forEach(key => console.log(`  - ${key}`));
    }
  }
  
  return {
    hasErrors,
    stats: {
      namespace,
      nl: keys.nl.length,
      en: keys.en.length,
      missing: missing.length,
      extra: extra.length
    }
  };
}

/**
 * Main function
 */
function main() {
  console.log(`${colors.blue}
╔═══════════════════════════════════════════════════════════╗
║         Translation Completeness Checker                  ║
║         Checking Dutch (nl) vs English (en)               ║
╚═══════════════════════════════════════════════════════════╝
${colors.reset}`);
  
  const allStats = [];
  let totalErrors = false;
  
  // Check each namespace
  for (const namespace of NAMESPACES) {
    const result = checkNamespace(namespace);
    
    if (result.hasErrors) {
      totalErrors = true;
    }
    
    if (result.stats) {
      allStats.push(result.stats);
    }
  }
  
  // Print summary
  console.log(`\n${colors.cyan}Summary${colors.reset}`);
  console.log('='.repeat(60));
  
  if (allStats.length > 0) {
    console.log('\nNamespace Statistics:');
    console.log('┌─────────────┬────────┬────────┬─────────┬───────┐');
    console.log('│ Namespace   │ NL     │ EN     │ Missing │ Extra │');
    console.log('├─────────────┼────────┼────────┼─────────┼───────┤');
    
    let totalNL = 0;
    let totalEN = 0;
    let totalMissing = 0;
    let totalExtra = 0;
    
    allStats.forEach(stat => {
      console.log(
        `│ ${stat.namespace.padEnd(11)} │ ${String(stat.nl).padStart(6)} │ ${String(stat.en).padStart(6)} │ ${String(stat.missing).padStart(7)} │ ${String(stat.extra).padStart(5)} │`
      );
      
      totalNL += stat.nl;
      totalEN += stat.en;
      totalMissing += stat.missing;
      totalExtra += stat.extra;
    });
    
    console.log('├─────────────┼────────┼────────┼─────────┼───────┤');
    console.log(
      `│ ${colors.cyan}TOTAL${colors.reset}       │ ${String(totalNL).padStart(6)} │ ${String(totalEN).padStart(6)} │ ${String(totalMissing).padStart(7)} │ ${String(totalExtra).padStart(5)} │`
    );
    console.log('└─────────────┴────────┴────────┴─────────┴───────┘');
    
    console.log(`\nTotal translation keys: ${totalNL} (Dutch), ${totalEN} (English)`);
    
    if (totalMissing > 0) {
      console.log(`${colors.red}Missing translations: ${totalMissing}${colors.reset}`);
    }
    
    if (totalExtra > 0) {
      console.log(`${colors.yellow}Extra translations: ${totalExtra}${colors.reset}`);
    }
  }
  
  // Exit with appropriate code
  if (totalErrors) {
    console.log(`\n${colors.red}✗ Translation check failed!${colors.reset}`);
    process.exit(1);
  } else {
    console.log(`\n${colors.green}✓ All translations are complete!${colors.reset}`);
    process.exit(0);
  }
}

// Run the script
main();
