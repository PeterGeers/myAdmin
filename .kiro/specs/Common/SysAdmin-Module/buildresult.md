cd "c:\Users\peter\aws\myAdmin\frontend" ; npm run build

> frontend@0.1.0 build
> set NODE_OPTIONS=--no-deprecation && set DISABLE_ESLINT_PLUGIN=false && react-scripts build

Creating an optimized production build...
Compiled with warnings.

[eslint]
src\components\TenantAdmin\UserManagement.tsx
Line 3:24: 'Heading' is defined but never used @typescript-eslint/no-unused-vars
Line 6:3: 'Divider' is defined but never used @typescript-eslint/no-unused-vars

Search for the keywords to learn more about each warning.
To ignore, add // eslint-disable-next-line to the line before.

File sizes after gzip:

1.38 MB build\static\js\537.587e8491.chunk.js
419.4 kB (-10.12 kB) build\static\js\main.caadb980.js
15.41 kB build\static\js\182.90bd60e7.chunk.js
1.76 kB build\static\js\453.8701dc61.chunk.js
263 B build\static\css\main.e6c13ad2.css

The bundle size is significantly larger than recommended.
Consider reducing it with code splitting: https://goo.gl/9VhYWB
You can also analyze the project dependencies: https://goo.gl/LeUzfb

The project was built assuming it is hosted at ./.
You can control this with the homepage field in your package.json.

The build folder is ready to be deployed.

Find out more about deployment here:

https://cra.link/deployment
