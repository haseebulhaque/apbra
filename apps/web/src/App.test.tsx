import {it, expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {App} from './App';
it('renders labelled input and honest unavailable release state', () => {
  const html=renderToStaticMarkup(<App/>);
  expect(html).toContain('for="prompt"');
  for(const id of ['sales-definition','yoy-coverage','region-security']) expect(html).toContain(`for="${id}"`);
  expect(html.match(/NOT_RUN/g)).toHaveLength(6);
  expect(html).toContain('No generated candidate or release package exists.');
  expect(html).toContain('disabled="">Download release package');
  expect(html).not.toContain('href=');
});
