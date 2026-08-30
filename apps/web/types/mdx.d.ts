declare module '*.mdx' {
  import { ComponentType } from 'react';
  interface MDXProps {
    components?: Record<string, ComponentType<any>>;
  }
  const MDXComponent: ComponentType<MDXProps>;
  export default MDXComponent;
}