/**
 * Configured PrismJS instance preloaded with all documentation and FODA code grammars
 * (`markup`, `css`, `clike`, `javascript`, `typescript`, `python`, `julia`, `bash`, `json`, `yaml`, `toml`).
 */
import Prism from './prismCore'

// Import Prism grammars strictly after prismCore has bound globalThis.Prism
import 'prismjs/components/prism-markup'
import 'prismjs/components/prism-css'
import 'prismjs/components/prism-clike'
import 'prismjs/components/prism-javascript'
import 'prismjs/components/prism-typescript'
import 'prismjs/components/prism-python'
import 'prismjs/components/prism-julia'
import 'prismjs/components/prism-bash'
import 'prismjs/components/prism-json'
import 'prismjs/components/prism-yaml'
import 'prismjs/components/prism-toml'

export default Prism
