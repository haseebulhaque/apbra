import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {expect, it} from 'vitest';
import {NativeInvitationAdmin} from './NativeInvitationAdmin';

it('labels address delivery and exposes only the accepted roles after scope resolution', () => {
  const markup=renderToStaticMarkup(<NativeInvitationAdmin csrf="synthetic" companyId="first" membershipId="manager"/>);
  expect(markup).toContain('Colleague email');
  expect(markup).toContain('<fieldset disabled="">');
  for(const role of ['MEMBER','EXPERT','COMPANY_ADMIN'])expect(markup).toContain('value="'+role+'"');
  expect(markup).not.toContain('COMPANY_OWNER');
  expect(markup).not.toContain('subject');
  expect(markup).not.toContain('synthetic');
});
