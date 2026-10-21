// Extracts a CloudFront Function's JS body from a Terraform `.tf` file and loads it
// as a callable `handler`, with the `cloudfront` module dependency-injected.
//
// Why read the .tf directly: the deployed function source lives inline in the
// Terraform heredoc (`code = <<-EOF ... EOF`) — CloudFront functions must be
// self-contained, so there is no separate .js artifact to import. Rather than
// DUPLICATE the handler into the test (which would silently drift from the
// deployed code), the test harness extracts the EXACT heredoc body and evaluates
// it against a mock `cf`. One source of truth: `infrastructure/application-form.tf`.
//
// This module has no third-party dependencies (Node >= 18 built-ins only), so the
// `infrastructure/` plane gets a committed JS test without a new toolchain.

import { readFile } from 'node:fs/promises';

/**
 * Pull the `code = <<-EOF ... EOF` heredoc for a named `aws_cloudfront_function`
 * resource out of a Terraform file.
 *
 * @param {string} tfPath absolute path to the .tf file
 * @param {string} resourceName the aws_cloudfront_function resource name
 * @returns {Promise<string>} the dedented JS body of the function's `code`
 */
export async function extractFunctionCode(tfPath, resourceName) {
  const tf = await readFile(tfPath, 'utf8');

  // Locate the resource block, then the first `code = <<-EOF ... EOF` within it.
  const resourceRe = new RegExp(
    `resource\\s+"aws_cloudfront_function"\\s+"${resourceName}"\\s*{`,
  );
  const resourceMatch = resourceRe.exec(tf);
  if (!resourceMatch) {
    throw new Error(`resource aws_cloudfront_function "${resourceName}" not found in ${tfPath}`);
  }
  const fromResource = tf.slice(resourceMatch.index);

  // `<<-EOF` is an indented heredoc: Terraform strips the LEADING indentation of the
  // closing marker from every line. Match the body between `<<-EOF` and the closing
  // `EOF` line.
  const heredocRe = /code\s*=\s*<<-?([A-Z]+)\n([\s\S]*?)\n\s*\1\b/;
  const heredoc = heredocRe.exec(fromResource);
  if (!heredoc) {
    throw new Error(`no code heredoc found for "${resourceName}"`);
  }
  const rawBody = heredoc[2];

  // Dedent: Terraform `<<-` removes the smallest leading-whitespace run common to the
  // block. Compute it from non-blank lines and strip it, mirroring the deploy.
  const lines = rawBody.split('\n');
  const indents = lines
    .filter((l) => l.trim().length > 0)
    .map((l) => (l.match(/^[ \t]*/) || [''])[0].length);
  const minIndent = indents.length ? Math.min(...indents) : 0;
  return lines.map((l) => l.slice(minIndent)).join('\n');
}

/**
 * Turn the extracted CloudFront-function source into a callable `handler`,
 * injecting a mock `cf` (the `cloudfront` runtime module) so no deploy/edge is
 * needed. Terraform `${...}` interpolations (e.g. the KVS id) are replaced with a
 * test placeholder before evaluation.
 *
 * @param {string} code the extracted function body
 * @param {object} cf the mock `cloudfront` module (supplies `cf.kvs(id)`)
 * @returns {Function} the async `handler(event)` the edge would invoke
 */
export function loadHandler(code, cf) {
  // Replace the `import cf from 'cloudfront';` line — the module only exists on the
  // CloudFront edge — with nothing; `cf` is provided as a parameter instead.
  let src = code.replace(/^\s*import\s+cf\s+from\s+'cloudfront';\s*$/m, '');

  // Neutralise any remaining Terraform interpolations (`${aws_...id}`) so the JS parses.
  src = src.replace(/\$\{[^}]*\}/g, 'TF_INTERP_PLACEHOLDER');

  // The body declares `async function handler(event)` plus module-level setup
  // (kvs binding). Wrap it in a factory that receives `cf` and returns `handler`.
  // eslint-disable-next-line no-new-func
  const factory = new Function(
    'cf',
    `${src}\n;return handler;`,
  );
  return factory(cf);
}
