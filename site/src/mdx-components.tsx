import defaultMdxComponents from 'fumadocs-ui/mdx';
import { Step, Steps } from 'fumadocs-ui/components/steps';
import { TypeTable } from 'fumadocs-ui/components/type-table';
import { CodeBlock, Pre } from 'fumadocs-ui/components/codeblock';
import * as TabsComponents from 'fumadocs-ui/components/tabs';
import type { MDXComponents } from 'mdx/types';
import type { ComponentPropsWithoutRef } from 'react';
import { name } from '@/lib/name';

/** The protocol's name, from the single config value in src/lib/name.ts. */
function ProtocolName() {
  return <>{name}</>;
}

export function getMDXComponents(components?: MDXComponents): MDXComponents {
  return {
    ...defaultMdxComponents,
    ...TabsComponents,
    Step,
    Steps,
    TypeTable,
    ProtocolName,
    pre: (props: ComponentPropsWithoutRef<'pre'>) => (
      <CodeBlock keepBackground {...props}>
        <Pre>{props.children}</Pre>
      </CodeBlock>
    ),
    ...components,
  };
}
