import yaml

spec = yaml.safe_load(open('backend/src/openapi_spec.yaml', 'r', encoding='utf-8'))
paths = spec['paths']
print(f'Total paths: {len(paths)}')
print('\nAll paths:')
for path in sorted(paths.keys()):
    print(f'  {path}')
