<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import {
    Check,
    ChevronDown,
    Code2,
    Columns2,
    Copy,
    Eye,
    FilePenLine,
    FilePlus2,
    FileText,
    Heading2,
    List,
    Lock,
    Pencil,
    RefreshCcw,
    Save,
    Search,
    Table,
    Trash2,
    X,
} from 'lucide-vue-next'
import apiClient from '../../api/client'
import { useDashboardStore } from '../../stores/dashboard'
import { renderMarkdown } from '../../utils/markdownRenderer'

interface CatalogArticle {
    id: string
    slug?: string
    title: string
    section: string
    locked: boolean
    source: 'builtin' | 'custom'
    updated_at?: string
}

interface CatalogSection {
    title: string
    articles: CatalogArticle[]
}

interface ArticleDetail extends CatalogArticle {
    content: string
}

const store = useDashboardStore()

const catalogSections = ref<CatalogSection[]>([])
const customArticles = ref<CatalogArticle[]>([])
const isCatalogLoading = ref(false)
const catalogError = ref<string | null>(null)
const catalogQuery = ref('')

const selectedArticleId = ref<string | null>(null)
const currentArticle = ref<ArticleDetail | null>(null)
const isArticleLoading = ref(false)
const articleError = ref<string | null>(null)

const isNewDraft = ref(false)
const draftTitle = ref('')
const draftSection = ref('Custom Articles')
const draftContent = ref('')
const savedTitleSnapshot = ref('')
const savedSectionSnapshot = ref('')
const savedContentSnapshot = ref('')

const viewMode = ref<'read' | 'split' | 'edit'>('read')
const isSaving = ref(false)
const isDeleting = ref(false)
const confirmingDelete = ref(false)
const copiedRaw = ref(false)
const actionBanner = ref<{ type: 'success' | 'error'; text: string } | null>(null)
const editorTextareaRef = ref<HTMLTextAreaElement | null>(null)

const showBanner = (type: 'success' | 'error', text: string) => {
    actionBanner.value = { type, text }
    setTimeout(() => {
        if (actionBanner.value?.text === text) {
            actionBanner.value = null
        }
    }, 3000)
}

const allArticlesFlat = computed<CatalogArticle[]>(() => {
    const out: CatalogArticle[] = [...customArticles.value]
    for (const sec of catalogSections.value) {
        out.push(...sec.articles)
    }
    return out
})

const builtinArticleCount = computed(() =>
    catalogSections.value.reduce((sum, s) => sum + s.articles.length, 0)
)

const filteredCustomArticles = computed<CatalogArticle[]>(() => {
    const q = catalogQuery.value.trim().toLowerCase()
    if (!q) return customArticles.value
    return customArticles.value.filter(
        (a) => a.title.toLowerCase().includes(q) || a.section.toLowerCase().includes(q)
    )
})

const filteredBuiltinSections = computed<CatalogSection[]>(() => {
    const q = catalogQuery.value.trim().toLowerCase()
    if (!q) return catalogSections.value
    const matched: CatalogSection[] = []
    for (const sec of catalogSections.value) {
        const secMatches = sec.title.toLowerCase().includes(q)
        const matchingArticles = secMatches
            ? sec.articles
            : sec.articles.filter((a) => a.title.toLowerCase().includes(q) || a.id.toLowerCase().includes(q))
        if (matchingArticles.length > 0) {
            matched.push({ title: sec.title, articles: matchingArticles })
        }
    }
    return matched
})

const isEditableActive = computed(() => {
    if (isNewDraft.value) return true
    return Boolean(currentArticle.value && !currentArticle.value.locked)
})

const hasUnsavedChanges = computed(() => {
    if (isNewDraft.value) {
        return Boolean(draftTitle.value.trim() || draftContent.value.trim())
    }
    if (!currentArticle.value || currentArticle.value.locked) return false
    return (
        draftTitle.value !== savedTitleSnapshot.value ||
        draftSection.value !== savedSectionSnapshot.value ||
        draftContent.value !== savedContentSnapshot.value
    )
})

const activeMarkdownSource = computed(() => {
    if (isEditableActive.value) return draftContent.value
    return currentArticle.value?.content || ''
})

const renderedMarkdownHtml = computed(() => renderMarkdown(activeMarkdownSource.value))

const loadCatalog = async (preserveSelection = true) => {
    isCatalogLoading.value = true
    catalogError.value = null
    try {
        const resp = await apiClient.get('/api/docs')
        catalogSections.value = Array.isArray(resp.data?.sections) ? resp.data.sections : []
        customArticles.value = Array.isArray(resp.data?.custom_articles) ? resp.data.custom_articles : []

        if (!preserveSelection || (!selectedArticleId.value && !isNewDraft.value)) {
            const firstBuiltin = catalogSections.value[0]?.articles?.[0]?.id
            const firstCustom = customArticles.value[0]?.id
            const initialId = firstBuiltin || firstCustom || null
            if (initialId) {
                await selectArticle(initialId)
            }
        }
    } catch (err: any) {
        catalogError.value = err?.response?.data?.detail || 'Failed to load documentation catalog.'
    } finally {
        isCatalogLoading.value = false
    }
}

const selectArticle = async (articleId: string) => {
    isNewDraft.value = false
    confirmingDelete.value = false
    selectedArticleId.value = articleId
    isArticleLoading.value = true
    articleError.value = null
    try {
        const resp = await apiClient.get('/api/docs/article', { params: { id: articleId } })
        const data: ArticleDetail = resp.data
        currentArticle.value = data
        if (!data.locked) {
            draftTitle.value = data.title
            draftSection.value = data.section || 'Custom Articles'
            draftContent.value = data.content || ''
            savedTitleSnapshot.value = draftTitle.value
            savedSectionSnapshot.value = draftSection.value
            savedContentSnapshot.value = draftContent.value
        } else {
            viewMode.value = 'read'
        }
    } catch (err: any) {
        articleError.value = err?.response?.data?.detail || 'Failed to load article content.'
        currentArticle.value = null
    } finally {
        isArticleLoading.value = false
    }
}

const startNewArticle = () => {
    confirmingDelete.value = false
    articleError.value = null
    selectedArticleId.value = null
    currentArticle.value = null
    isNewDraft.value = true
    draftTitle.value = ''
    draftSection.value = 'Custom Articles'
    draftContent.value = '# New Technical Note\n\nWrite your engineering observations or runbook notes here.\n\n- Key finding 1\n- Key finding 2\n'
    savedTitleSnapshot.value = ''
    savedSectionSnapshot.value = 'Custom Articles'
    savedContentSnapshot.value = ''
    viewMode.value = 'split'
}

const duplicateBuiltinToCustom = async () => {
    if (!currentArticle.value) return
    isSaving.value = true
    try {
        const resp = await apiClient.post('/api/docs/custom', {
            title: `${currentArticle.value.title} (Notes)`,
            section: 'Custom Articles',
            content: currentArticle.value.content || '',
        })
        const created: ArticleDetail = resp.data
        await loadCatalog(true)
        await selectArticle(created.id)
        viewMode.value = 'edit'
        showBanner('success', `Duplicated to editable note "${created.title}".`)
    } catch (err: any) {
        showBanner('error', err?.response?.data?.detail || 'Could not duplicate article.')
    } finally {
        isSaving.value = false
    }
}

const saveCustomArticle = async () => {
    const cleanTitle = draftTitle.value.trim()
    if (!cleanTitle) {
        showBanner('error', 'Article title cannot be empty.')
        return
    }
    const cleanSection = draftSection.value.trim() || 'Custom Articles'
    isSaving.value = true
    try {
        let saved: ArticleDetail
        if (isNewDraft.value) {
            const resp = await apiClient.post('/api/docs/custom', {
                title: cleanTitle,
                section: cleanSection,
                content: draftContent.value,
            })
            saved = resp.data
        } else if (currentArticle.value?.slug) {
            const resp = await apiClient.put(`/api/docs/custom/${encodeURIComponent(currentArticle.value.slug)}`, {
                title: cleanTitle,
                section: cleanSection,
                content: draftContent.value,
            })
            saved = resp.data
        } else {
            return
        }

        isNewDraft.value = false
        selectedArticleId.value = saved.id
        currentArticle.value = saved
        draftTitle.value = saved.title
        draftSection.value = saved.section
        draftContent.value = saved.content
        savedTitleSnapshot.value = saved.title
        savedSectionSnapshot.value = saved.section
        savedContentSnapshot.value = saved.content
        await loadCatalog(true)
        showBanner('success', `Saved "${saved.title}" to docs/custom/${saved.slug}.md`)
    } catch (err: any) {
        showBanner('error', err?.response?.data?.detail || 'Failed to save custom article.')
    } finally {
        isSaving.value = false
    }
}

const deleteActiveCustomArticle = async () => {
    const slug = currentArticle.value?.slug
    if (!slug) return
    isDeleting.value = true
    try {
        await apiClient.delete(`/api/docs/custom/${encodeURIComponent(slug)}`)
        confirmingDelete.value = false
        currentArticle.value = null
        selectedArticleId.value = null
        await loadCatalog(false)
        showBanner('success', 'Deleted custom article.')
    } catch (err: any) {
        showBanner('error', err?.response?.data?.detail || 'Failed to delete article.')
    } finally {
        isDeleting.value = false
    }
}

const copyRawMarkdown = async () => {
    const md = activeMarkdownSource.value
    if (!md) return
    try {
        if (typeof navigator !== 'undefined' && navigator.clipboard) {
            await navigator.clipboard.writeText(md)
        }
        copiedRaw.value = true
        setTimeout(() => {
            copiedRaw.value = false
        }, 1500)
    } catch {
        // Ignore clipboard errors in restricted contexts
    }
}

const insertSnippet = (before: string, after = '', placeholder = '') => {
    const el = editorTextareaRef.value
    if (!el) {
        draftContent.value += `${before}${placeholder}${after}`
        return
    }
    const start = el.selectionStart ?? draftContent.value.length
    const end = el.selectionEnd ?? draftContent.value.length
    const selected = draftContent.value.slice(start, end) || placeholder
    const replacement = `${before}${selected}${after}`
    draftContent.value =
        draftContent.value.slice(0, start) + replacement + draftContent.value.slice(end)
    nextTick(() => {
        el.focus()
        const cursorPos = start + before.length + selected.length
        el.setSelectionRange(cursorPos, cursorPos)
    })
}

const resolveRelativeDocId = (baseId: string, relHref: string): string => {
    const cleanRel = relHref.split('#')[0].split('?')[0].trim()
    if (!cleanRel) return baseId
    const baseParts = baseId.includes('/') ? baseId.split('/').slice(0, -1) : []
    for (const seg of cleanRel.split('/')) {
        if (!seg || seg === '.') continue
        if (seg === '..') {
            baseParts.pop()
        } else {
            baseParts.push(seg)
        }
    }
    return baseParts.join('/')
}

const handleMarkdownClick = (event: MouseEvent) => {
    const target = event.target as HTMLElement | null
    const docAnchor = target?.closest('a[data-doc-link]') as HTMLAnchorElement | null
    if (!docAnchor) return
    event.preventDefault()
    const rawHref = docAnchor.getAttribute('data-doc-link') || ''
    const baseId = selectedArticleId.value || 'index.md'
    const candidateId = resolveRelativeDocId(baseId, rawHref)
    const match = allArticlesFlat.value.find(
        (a) => a.id === candidateId || a.id === candidateId.replace(/\.md$/i, '')
    )
    if (match) {
        selectArticle(match.id)
    }
}

onMounted(() => {
    loadCatalog(false)
})
</script>

<template>
  <div class="h-full w-full flex overflow-hidden"
       :class="store.theme === 'dark' ? 'bg-slate-900 text-slate-100' : 'bg-white text-slate-800'">

    <!-- Portal Catalog Summary & Actions into Global Header -->
    <Teleport defer to="#view-header-actions">
      <div class="flex items-center gap-2 shrink-0">
        <span class="hidden sm:inline-flex items-center px-2 py-1 rounded-md border text-[10px] font-mono font-semibold whitespace-nowrap"
              :class="store.theme === 'dark' ? 'bg-slate-800/80 border-white/10 text-slate-300' : 'bg-slate-100 border-slate-200 text-slate-600'">
          {{ builtinArticleCount }} Reference · {{ customArticles.length }} Custom
        </span>
        <button @click="loadCatalog(true)"
                type="button"
                class="p-1.5 rounded-md border text-slate-400 hover:text-[#00305E] dark:hover:text-sky-400 transition-colors cursor-pointer"
                :class="store.theme === 'dark' ? 'border-white/10 bg-slate-800 hover:bg-slate-700' : 'border-slate-200 bg-white hover:bg-slate-100'"
                title="Reload documentation index">
          <RefreshCcw :size="13" :class="isCatalogLoading ? 'animate-spin' : ''" />
        </button>
        <button @click="startNewArticle"
                type="button"
                class="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md text-[11px] font-bold bg-[#00305E] hover:bg-[#004482] text-white transition-colors cursor-pointer shadow-xs"
                title="Create a new editable Markdown article">
          <FilePlus2 :size="12" />
          <span>+ New Article</span>
        </button>
      </div>
    </Teleport>

    <!-- LEFT PANE: ARTICLE CATALOG SIDEBAR -->
    <aside class="w-64 lg:w-72 shrink-0 border-r flex flex-col min-h-0"
           :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/10' : 'bg-slate-50/70 border-slate-200'">

      <!-- Catalog Filter -->
      <div class="px-3 py-2.5 border-b shrink-0"
           :class="store.theme === 'dark' ? 'border-white/10' : 'border-slate-200/80'">
        <div class="relative">
          <Search :size="12" class="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
          <input v-model="catalogQuery"
                 type="text"
                 placeholder="Search articles..."
                 class="w-full pl-7 pr-7 py-1.5 rounded-md border text-xs outline-none transition-colors"
                 :class="store.theme === 'dark'
                   ? 'bg-slate-900 border-white/10 text-white placeholder:text-slate-500 focus:border-sky-400/50'
                   : 'bg-white border-slate-200 text-slate-800 placeholder:text-slate-400 focus:border-[#00305E]'" />
          <button v-if="catalogQuery"
                  @click="catalogQuery = ''"
                  type="button"
                  class="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 cursor-pointer"
                  title="Clear search">
            <X :size="12" />
          </button>
        </div>
      </div>

      <!-- Scrollable Section Tree -->
      <div class="flex-1 overflow-y-auto p-2.5 space-y-2 custom-scrollbar">
        <div v-if="catalogError"
             class="p-2.5 rounded-md border text-[11px] bg-rose-500/10 border-rose-500/25 text-rose-600 dark:text-rose-400">
          {{ catalogError }}
        </div>

        <!-- Custom Articles Section -->
        <details open class="group">
          <summary class="flex items-center justify-between px-2 py-1.5 rounded text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 cursor-pointer select-none list-none [&::-webkit-details-marker]:hidden hover:text-slate-800 dark:hover:text-slate-200">
            <span>Custom Articles ({{ filteredCustomArticles.length }})</span>
            <ChevronDown :size="12" class="transition-transform group-open:rotate-180" />
          </summary>

          <div class="mt-1 space-y-0.5 pl-1">
            <button v-for="art in filteredCustomArticles"
                    :key="art.id"
                    @click="selectArticle(art.id)"
                    type="button"
                    class="w-full flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-md text-left text-xs transition-colors cursor-pointer"
                    :class="selectedArticleId === art.id && !isNewDraft
                      ? 'bg-[#00305E] text-white font-semibold shadow-2xs dark:bg-sky-500/20 dark:text-sky-200 dark:border dark:border-sky-400/30'
                      : (store.theme === 'dark' ? 'text-slate-300 hover:bg-white/5' : 'text-slate-700 hover:bg-slate-200/70')">
              <span class="flex items-center gap-1.5 min-w-0">
                <FilePenLine :size="12" class="shrink-0 opacity-80" />
                <span class="truncate">{{ art.title }}</span>
              </span>
            </button>

            <div v-if="filteredCustomArticles.length === 0"
                 class="px-2.5 py-2 text-[11px] text-slate-400 italic">
              {{ catalogQuery ? 'No matching custom articles.' : 'No custom articles yet — click + New.' }}
            </div>
          </div>
        </details>

        <div class="border-t pt-1" :class="store.theme === 'dark' ? 'border-white/5' : 'border-slate-200/70'"></div>

        <!-- Built-in Reference Sections (Locked) -->
        <details v-for="sec in filteredBuiltinSections"
                 :key="sec.title"
                 open
                 class="group">
          <summary class="flex items-center justify-between px-2 py-1.5 rounded text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 cursor-pointer select-none list-none [&::-webkit-details-marker]:hidden hover:text-slate-800 dark:hover:text-slate-200">
            <span class="truncate">{{ sec.title }}</span>
            <ChevronDown :size="12" class="shrink-0 transition-transform group-open:rotate-180" />
          </summary>

          <div class="mt-0.5 space-y-0.5 pl-1">
            <button v-for="art in sec.articles"
                    :key="art.id"
                    @click="selectArticle(art.id)"
                    type="button"
                    class="w-full flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-md text-left text-xs transition-colors cursor-pointer"
                    :class="selectedArticleId === art.id && !isNewDraft
                      ? 'bg-[#00305E] text-white font-semibold shadow-2xs dark:bg-sky-500/20 dark:text-sky-200 dark:border dark:border-sky-400/30'
                      : (store.theme === 'dark' ? 'text-slate-300 hover:bg-white/5' : 'text-slate-700 hover:bg-slate-200/70')">
              <span class="flex items-center gap-1.5 min-w-0">
                <FileText :size="12" class="shrink-0 opacity-70" />
                <span class="truncate">{{ art.title }}</span>
              </span>
              <Lock :size="10" class="shrink-0 opacity-50" title="Locked reference article" />
            </button>
          </div>
        </details>
      </div>
    </aside>

    <!-- RIGHT PANE: MARKDOWN READER & EDITOR -->
    <section class="flex-1 min-w-0 flex flex-col overflow-hidden">

      <!-- Top Article Toolbar -->
      <div class="px-5 py-2.5 border-b flex flex-wrap items-center justify-between gap-3 shrink-0"
           :class="store.theme === 'dark' ? 'border-white/10 bg-slate-900/90' : 'border-slate-200 bg-white'">
        <div class="min-w-0 space-y-0.5">
          <div class="flex items-center gap-2 flex-wrap">
            <span class="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              {{ isNewDraft ? (draftSection || 'Custom Articles') : (currentArticle?.section || 'Documentation') }}
            </span>

            <span v-if="!isNewDraft && currentArticle?.locked"
                  class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold border"
                  :class="store.theme === 'dark' ? 'bg-white/5 border-white/10 text-slate-300' : 'bg-slate-100 border-slate-200 text-slate-600'">
              <Lock :size="10" />
              Locked · Reference
            </span>

            <span v-else-if="isEditableActive"
                  class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold border bg-emerald-500/10 border-emerald-500/25 text-emerald-700 dark:text-emerald-300">
              <FilePenLine :size="10" />
              {{ isNewDraft ? 'New Draft' : 'Editable · Custom' }}
            </span>

            <span v-if="hasUnsavedChanges"
                  class="px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30">
              Unsaved changes
            </span>
          </div>

          <h3 class="text-sm font-bold truncate" :class="store.theme === 'dark' ? 'text-white' : 'text-slate-900'">
            {{ isNewDraft ? (draftTitle || 'Untitled Custom Article') : (currentArticle?.title || 'Select an article') }}
          </h3>
        </div>

        <!-- Toolbar Actions -->
        <div class="flex items-center gap-2 flex-wrap shrink-0">
          <!-- Copy Raw Markdown -->
          <button v-if="currentArticle || isNewDraft"
                  @click="copyRawMarkdown"
                  type="button"
                  class="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md border text-[11px] font-semibold transition-colors cursor-pointer"
                  :class="store.theme === 'dark' ? 'border-white/10 bg-slate-800 text-slate-300 hover:text-white' : 'border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100'">
            <Check v-if="copiedRaw" :size="12" class="text-emerald-500" />
            <Copy v-else :size="12" />
            <span>{{ copiedRaw ? 'Copied' : 'Copy MD' }}</span>
          </button>

          <!-- Built-in Readonly Actions -->
          <button v-if="currentArticle?.locked"
                  @click="duplicateBuiltinToCustom"
                  :disabled="isSaving"
                  type="button"
                  class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border text-[11px] font-semibold transition-colors cursor-pointer"
                  :class="store.theme === 'dark' ? 'border-sky-500/30 bg-sky-500/10 text-sky-300 hover:bg-sky-500/20' : 'border-[#00305E]/25 bg-[#00305E]/5 text-[#00305E] hover:bg-[#00305E]/10'">
            <FilePlus2 :size="12" />
            <span>Duplicate as Custom</span>
          </button>

          <!-- Custom Editable Actions -->
          <template v-if="isEditableActive">
            <div class="flex items-center p-0.5 rounded-md border text-[11px] font-semibold"
                 :class="store.theme === 'dark' ? 'bg-slate-950 border-white/10' : 'bg-slate-100 border-slate-200'">
              <button @click="viewMode = 'read'"
                      type="button"
                      class="inline-flex items-center gap-1 px-2 py-1 rounded transition-colors cursor-pointer"
                      :class="viewMode === 'read' ? 'bg-[#00305E] text-white shadow-xs' : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'">
                <Eye :size="11" />
                <span>Read</span>
              </button>
              <button @click="viewMode = 'split'"
                      type="button"
                      class="inline-flex items-center gap-1 px-2 py-1 rounded transition-colors cursor-pointer"
                      :class="viewMode === 'split' ? 'bg-[#00305E] text-white shadow-xs' : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'">
                <Columns2 :size="11" />
                <span>Split</span>
              </button>
              <button @click="viewMode = 'edit'"
                      type="button"
                      class="inline-flex items-center gap-1 px-2 py-1 rounded transition-colors cursor-pointer"
                      :class="viewMode === 'edit' ? 'bg-[#00305E] text-white shadow-xs' : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'">
                <Pencil :size="11" />
                <span>Edit</span>
              </button>
            </div>

            <button @click="saveCustomArticle"
                    :disabled="isSaving"
                    type="button"
                    class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[11px] font-bold bg-[#00305E] hover:bg-[#004482] text-white transition-colors cursor-pointer disabled:opacity-50">
              <Save :size="12" />
              <span>{{ isSaving ? 'Saving...' : 'Save' }}</span>
            </button>

            <template v-if="!isNewDraft && currentArticle?.slug">
              <button v-if="!confirmingDelete"
                      @click="confirmingDelete = true"
                      type="button"
                      class="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md border text-[11px] font-semibold border-rose-500/30 bg-rose-500/10 text-rose-600 dark:text-rose-400 hover:bg-rose-500/20 cursor-pointer">
                <Trash2 :size="12" />
                <span>Delete</span>
              </button>

              <div v-else class="flex items-center gap-1">
                <button @click="deleteActiveCustomArticle"
                        :disabled="isDeleting"
                        type="button"
                        class="px-2.5 py-1.5 rounded-md text-[11px] font-bold bg-rose-600 hover:bg-rose-700 text-white cursor-pointer disabled:opacity-50">
                  {{ isDeleting ? 'Deleting...' : 'Confirm Delete' }}
                </button>
                <button @click="confirmingDelete = false"
                        type="button"
                        class="px-2 py-1.5 rounded-md border text-[11px] font-semibold cursor-pointer"
                        :class="store.theme === 'dark' ? 'border-white/10 text-slate-300' : 'border-slate-200 text-slate-600'">
                  Cancel
                </button>
              </div>
            </template>
          </template>
        </div>
      </div>

      <!-- Notification Banner -->
      <div v-if="actionBanner"
           class="px-5 py-2 text-xs font-medium border-b shrink-0 flex items-center justify-between"
           :class="actionBanner.type === 'success'
             ? 'bg-emerald-500/10 border-emerald-500/25 text-emerald-700 dark:text-emerald-300'
             : 'bg-rose-500/10 border-rose-500/25 text-rose-700 dark:text-rose-300'">
        <span>{{ actionBanner.text }}</span>
        <button @click="actionBanner = null" type="button" class="cursor-pointer opacity-70 hover:opacity-100">
          <X :size="13" />
        </button>
      </div>

      <!-- Custom Article Metadata + Quick Markdown Strip (Edit / Split) -->
      <div v-if="isEditableActive && viewMode !== 'read'"
           class="px-5 py-2.5 border-b space-y-2 shrink-0"
           :class="store.theme === 'dark' ? 'bg-slate-950/50 border-white/10' : 'bg-slate-50 border-slate-200/80'">
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-2">
          <div class="sm:col-span-2">
            <label class="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-0.5">Title</label>
            <input v-model="draftTitle"
                   type="text"
                   placeholder="Article title..."
                   class="w-full px-2.5 py-1.5 rounded-md border text-xs font-semibold outline-none"
                   :class="store.theme === 'dark' ? 'bg-slate-900 border-white/10 text-white focus:border-sky-400/50' : 'bg-white border-slate-200 text-slate-900 focus:border-[#00305E]'" />
          </div>
          <div>
            <label class="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-0.5">Category</label>
            <input v-model="draftSection"
                   type="text"
                   placeholder="Custom Articles"
                   class="w-full px-2.5 py-1.5 rounded-md border text-xs outline-none"
                   :class="store.theme === 'dark' ? 'bg-slate-900 border-white/10 text-white focus:border-sky-400/50' : 'bg-white border-slate-200 text-slate-900 focus:border-[#00305E]'" />
          </div>
        </div>

        <div class="flex items-center gap-1.5 flex-wrap text-[11px]">
          <span class="text-[10px] font-bold uppercase tracking-wider text-slate-400 mr-1">Insert:</span>
          <button @click="insertSnippet('## ', '', 'Heading')" type="button"
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded border cursor-pointer"
                  :class="store.theme === 'dark' ? 'bg-slate-900 border-white/10 text-slate-300 hover:bg-slate-800' : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-100'">
            <Heading2 :size="11" /> H2
          </button>
          <button @click="insertSnippet('**', '**', 'bold text')" type="button"
                  class="px-2 py-0.5 rounded border font-bold cursor-pointer"
                  :class="store.theme === 'dark' ? 'bg-slate-900 border-white/10 text-slate-300 hover:bg-slate-800' : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-100'">
            B
          </button>
          <button @click="insertSnippet('```python\n', '\n```\n', 'print(\'hello\')')" type="button"
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded border font-mono cursor-pointer"
                  :class="store.theme === 'dark' ? 'bg-slate-900 border-white/10 text-slate-300 hover:bg-slate-800' : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-100'">
            <Code2 :size="11" /> Code
          </button>
          <button @click="insertSnippet('\n| Column A | Column B |\n| --- | --- |\n| Value 1 | Value 2 |\n')" type="button"
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded border cursor-pointer"
                  :class="store.theme === 'dark' ? 'bg-slate-900 border-white/10 text-slate-300 hover:bg-slate-800' : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-100'">
            <Table :size="11" /> Table
          </button>
          <button @click="insertSnippet('\n- ', '', 'List item')" type="button"
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded border cursor-pointer"
                  :class="store.theme === 'dark' ? 'bg-slate-900 border-white/10 text-slate-300 hover:bg-slate-800' : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-100'">
            <List :size="11" /> List
          </button>
          <button @click="insertSnippet('$$\n', '\n$$\n', 'E = mc^2')" type="button"
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded border cursor-pointer font-mono"
                  :class="store.theme === 'dark' ? 'bg-slate-900 border-white/10 text-slate-300 hover:bg-slate-800' : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-100'">
            <span>∑</span> Math
          </button>
        </div>
      </div>

      <!-- Main Body Area -->
      <div class="flex-1 min-h-0 overflow-hidden flex">
        <!-- Loading / Error Empty States -->
        <div v-if="isArticleLoading" class="flex-1 flex items-center justify-center text-xs text-slate-400">
          Loading article...
        </div>
        <div v-else-if="articleError" class="flex-1 flex items-center justify-center p-6">
          <div class="p-4 rounded-lg border bg-rose-500/10 border-rose-500/25 text-xs text-rose-600 dark:text-rose-400">
            {{ articleError }}
          </div>
        </div>

        <!-- Read or Split/Edit Panes -->
        <template v-else>
          <!-- Markdown Editor Textarea (in Edit or Split mode for custom articles) -->
          <div v-if="isEditableActive && viewMode !== 'read'"
               class="flex-1 min-w-0 flex flex-col h-full"
               :class="viewMode === 'split' ? (store.theme === 'dark' ? 'border-r border-white/10' : 'border-r border-slate-200') : ''">
            <textarea ref="editorTextareaRef"
                      v-model="draftContent"
                      spellcheck="false"
                      placeholder="Write Markdown content here..."
                      class="w-full h-full flex-1 p-5 font-mono text-xs leading-relaxed resize-none outline-none"
                      :class="store.theme === 'dark' ? 'bg-slate-950 text-slate-100' : 'bg-white text-slate-800'"></textarea>
          </div>

          <!-- Rendered Markdown Reader (in Read or Split mode) -->
          <div v-if="!isEditableActive || viewMode !== 'edit'"
               class="flex-1 min-w-0 h-full overflow-y-auto px-8 py-7 custom-scrollbar"
               @click="handleMarkdownClick">
            <article class="doc-prose max-w-4xl mx-auto"
                     :class="store.theme === 'dark' ? 'doc-prose-dark' : 'doc-prose-light'"
                     v-html="renderedMarkdownHtml"></article>
          </div>
        </template>
      </div>
    </section>
  </div>
</template>

<style scoped>
.doc-prose {
  font-size: 0.9rem;
  line-height: 1.7;
}

.doc-prose :deep(h1) {
  font-size: 1.55rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  margin-bottom: 0.9rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid rgba(148, 163, 184, 0.25);
}

.doc-prose :deep(h2) {
  font-size: 1.2rem;
  font-weight: 700;
  margin-top: 1.65rem;
  margin-bottom: 0.65rem;
  padding-bottom: 0.25rem;
  border-bottom: 1px solid rgba(148, 163, 184, 0.16);
}

.doc-prose-light :deep(h1),
.doc-prose-light :deep(h2),
.doc-prose-light :deep(h3) {
  color: #00305e;
}

.doc-prose-dark :deep(h1),
.doc-prose-dark :deep(h2),
.doc-prose-dark :deep(h3) {
  color: #e2e8f0;
}

.doc-prose :deep(h3) {
  font-size: 1.02rem;
  font-weight: 700;
  margin-top: 1.25rem;
  margin-bottom: 0.45rem;
}

.doc-prose :deep(h4) {
  font-size: 0.92rem;
  font-weight: 700;
  margin-top: 1rem;
  margin-bottom: 0.35rem;
}

.doc-prose :deep(p) {
  margin-bottom: 0.85rem;
}

.doc-prose :deep(ul),
.doc-prose :deep(ol) {
  margin-bottom: 0.9rem;
  padding-left: 1.4rem;
}

.doc-prose :deep(ul) {
  list-style-type: disc;
}

.doc-prose :deep(ol) {
  list-style-type: decimal;
}

.doc-prose :deep(li) {
  margin-bottom: 0.3rem;
}

.doc-prose :deep(hr) {
  border: 0;
  border-top: 1px solid rgba(148, 163, 184, 0.25);
  margin: 1.35rem 0;
}

.doc-prose :deep(.md-link) {
  color: #00305e;
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.doc-prose-dark :deep(.md-link) {
  color: #38bdf8;
}

.doc-prose :deep(.md-inline-code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.82em;
  padding: 0.12rem 0.38rem;
  border-radius: 0.25rem;
  background: rgba(148, 163, 184, 0.16);
}

.doc-prose :deep(.md-math-inline) {
  display: inline;
  color: inherit;
}

.doc-prose :deep(.md-math-inline .katex) {
  font-size: 1.03em;
}

.doc-prose :deep(.md-math-block) {
  margin: 1.05rem 0;
  padding: 0.85rem 1.15rem;
  border-radius: 0.5rem;
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: rgba(248, 250, 252, 0.75);
  text-align: center;
  overflow-x: auto;
  overflow-y: hidden;
}

.doc-prose-dark :deep(.md-math-block) {
  background: rgba(15, 23, 42, 0.75);
  border-color: rgba(255, 255, 255, 0.1);
  color: #f1f5f9;
}

.doc-prose :deep(.md-math-block .katex-display) {
  margin: 0;
}

.doc-prose :deep(.md-math-fallback) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.84em;
  color: #ef4444;
}

.doc-prose :deep(.md-code-block),
.doc-prose :deep(.md-mermaid-block) {
  margin: 1rem 0;
  border-radius: 0.375rem;
  overflow: hidden;
  border: 1px solid rgba(30, 41, 59, 0.85);
  background: #0f172a;
}

.doc-prose :deep(.md-code-header) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.35rem 0.8rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #94a3b8;
  background: #020617;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.doc-prose :deep(.md-code-pre) {
  margin: 0 !important;
  padding: 0.85rem 1rem !important;
  background: transparent !important;
  color: #e2e8f0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.78rem;
  line-height: 1.55;
  overflow-x: auto;
}

.doc-prose :deep(blockquote) {
  margin: 1rem 0;
  padding: 0.5rem 0.9rem;
  border-left: 3px solid #00305e;
  background: rgba(241, 245, 249, 0.65);
  border-radius: 0 0.375rem 0.375rem 0;
}

.doc-prose-dark :deep(blockquote) {
  border-left-color: #38bdf8;
  background: rgba(15, 23, 42, 0.7);
}

.doc-prose :deep(.md-admonition) {
  margin: 1rem 0;
  padding: 0.75rem 1rem;
  border-radius: 0.375rem;
  border: 1px solid rgba(148, 163, 184, 0.3);
  border-left-width: 4px;
  background: rgba(248, 250, 252, 0.75);
}

.doc-prose-dark :deep(.md-admonition) {
  background: rgba(15, 23, 42, 0.75);
  border-color: rgba(255, 255, 255, 0.1);
}

.doc-prose :deep(.md-admonition-note),
.doc-prose :deep(.md-admonition-info) {
  border-left-color: #00305e;
}

.doc-prose-dark :deep(.md-admonition-note),
.doc-prose-dark :deep(.md-admonition-info) {
  border-left-color: #38bdf8;
}

.doc-prose :deep(.md-admonition-tip),
.doc-prose :deep(.md-admonition-important) {
  border-left-color: #10b981;
}

.doc-prose :deep(.md-admonition-warning),
.doc-prose :deep(.md-admonition-danger) {
  border-left-color: #f59e0b;
}

.doc-prose :deep(.md-admonition-title) {
  font-size: 0.78rem;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 0.35rem;
}

.doc-prose :deep(.md-admonition-body > :last-child) {
  margin-bottom: 0;
}

.doc-prose :deep(.md-table-wrap) {
  margin: 1rem 0;
  overflow-x: auto;
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 0.375rem;
}

.doc-prose :deep(table) {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}

.doc-prose :deep(th),
.doc-prose :deep(td) {
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
}

.doc-prose :deep(th) {
  font-weight: 700;
  font-size: 0.74rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  background: rgba(241, 245, 249, 0.85);
}

.doc-prose-dark :deep(th) {
  background: rgba(15, 23, 42, 0.9);
}

.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.25);
  border-radius: 4px;
}
</style>
