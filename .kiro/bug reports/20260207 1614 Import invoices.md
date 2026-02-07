When opening Impiort invoices the folders in Facturen is loaded
In the folder Facturen there is 1 instance of Booking.com
If I search with google dribe i also see only 1

BUT

The logs shows installHook.js:1 Encountered two children with the same key, `Booking.com`. Keys should be unique so that components maintain their identity across updates. Non-unique keys may cause children to be duplicated and/or omitted — the behavior is unsupported and could change in a future version.
overrideMethod @ installHook.js:1
(anonymous) @ react-dom-client.development.js:6604
runWithFiberInDEV @ react-dom-client.development.js:870
warnOnInvalidKey @ react-dom-client.development.js:6603
reconcileChildrenArray @ react-dom-client.development.js:6669
reconcileChildFibersImpl @ react-dom-client.development.js:6990
(anonymous) @ react-dom-client.development.js:7098
reconcileChildren @ react-dom-client.development.js:9699
beginWork @ react-dom-client.development.js:11988
runWithFiberInDEV @ react-dom-client.development.js:870
performUnitOfWork @ react-dom-client.development.js:17639
workLoopSync @ react-dom-client.development.js:17469
renderRootSync @ react-dom-client.development.js:17450
performWorkOnRoot @ react-dom-client.development.js:16498
performWorkOnRootViaSchedulerTask @ react-dom-client.development.js:18957
performWorkUntilDeadline @ scheduler.development.js:45
<option>
exports.jsxDEV @ react-jsx-dev-runtime.development.js:327
(anonymous) @ PDFUploadForm.tsx:571
children @ PDFUploadForm.tsx:571
Formik @ Formik.tsx:1027
react_stack_bottom_frame @ react-dom-client.development.js:25904
renderWithHooksAgain @ react-dom-client.development.js:7762
renderWithHooks @ react-dom-client.development.js:7674
updateFunctionComponent @ react-dom-client.development.js:10166
beginWork @ react-dom-client.development.js:11778
runWithFiberInDEV @ react-dom-client.development.js:870
performUnitOfWork @ react-dom-client.development.js:17639
workLoopSync @ react-dom-client.development.js:17469
renderRootSync @ react-dom-client.development.js:17450
performWorkOnRoot @ react-dom-client.development.js:16498
performWorkOnRootViaSchedulerTask @ react-dom-client.development.js:18957
performWorkUntilDeadline @ scheduler.development.js:45
<Formik>
exports.jsxDEV @ react-jsx-dev-runtime.development.js:327
PDFUploadForm @ PDFUploadForm.tsx:521
react_stack_bottom_frame @ react-dom-client.development.js:25904
renderWithHooksAgain @ react-dom-client.development.js:7762
renderWithHooks @ react-dom-client.development.js:7674
updateFunctionComponent @ react-dom-client.development.js:10166
beginWork @ react-dom-client.development.js:11778
runWithFiberInDEV @ react-dom-client.development.js:870
performUnitOfWork @ react-dom-client.development.js:17639
workLoopSync @ react-dom-client.development.js:17469
renderRootSync @ react-dom-client.development.js:17450
performWorkOnRoot @ react-dom-client.development.js:16498
performSyncWorkOnRoot @ react-dom-client.development.js:18972
flushSyncWorkAcrossRoots_impl @ react-dom-client.development.js:18803
processRootScheduleInMicrotask @ react-dom-client.development.js:18851
(anonymous) @ react-dom-client.development.js:18986
<PDFUploadForm>
exports.jsxDEV @ react-jsx-dev-runtime.development.js:327
renderPage @ App.tsx:90
AppContent @ App.tsx:452
react_stack_bottom_frame @ react-dom-client.development.js:25904
renderWithHooksAgain @ react-dom-client.development.js:7762
renderWithHooks @ react-dom-client.development.js:7674
updateFunctionComponent @ react-dom-client.development.js:10166
beginWork @ react-dom-client.development.js:11778
runWithFiberInDEV @ react-dom-client.development.js:870
performUnitOfWork @ react-dom-client.development.js:17639
workLoopSync @ react-dom-client.development.js:17469
renderRootSync @ react-dom-client.development.js:17450
performWorkOnRoot @ react-dom-client.development.js:16498
performSyncWorkOnRoot @ react-dom-client.development.js:18972
flushSyncWorkAcrossRoots_impl @ react-dom-client.development.js:18803
processRootScheduleInMicrotask @ react-dom-client.development.js:18851
(anonymous) @ react-dom-client.development.js:18986Understand this error
installHook.js:1 Encountered two children with the same key, `Booking.com`. Keys should be unique so that components maintain their identity across updates. Non-unique keys may cause children to be duplicated and/or omitted — the behavior is unsupported and could change in a future version.