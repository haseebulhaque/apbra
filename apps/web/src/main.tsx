import React from 'react';
import {createRoot} from 'react-dom/client';
import {EnterpriseApp} from './EnterpriseApp';
import './style.css';
createRoot(document.getElementById('root')!).render(<React.StrictMode><EnterpriseApp/></React.StrictMode>);
