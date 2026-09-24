// Current public Asura pages, isolated from the preserved upstream checkout.
import * as cheerio from 'cheerio';
import { fetchHTML, fetchJSON } from '../utils/httpClient';
const BASE = 'https://asurascans.com';

// Astro serializes island props as [type, value] tuples.
export function decode(value: any): any {
    if (!Array.isArray(value) || value.length !== 2) return value;
    const [kind, data] = value;
    if (kind === 1) return data.map(decode);
    if (kind === 0 && data && typeof data === 'object') {
        return Object.fromEntries(Object.entries(data).map(([key, item]) => [key, decode(item)]));
    }
    return data;
}
export function island(html: string, component: string): any {
    const $ = cheerio.load(html);
    const raw = $(`astro-island[component-url*="${component}"]`).first().attr('props');
    if (!raw) throw new Error(`Missing public ${component} data`);
    return Object.fromEntries(Object.entries(JSON.parse(raw)).map(([key, value]) => [key, decode(value)]));
}
function seriesPath(slug: string): string {
    return slug.startsWith('comics/') ? slug : `comics/${slug}`;
}
export class AsuraScraper {
    async browse(page = 1, limit = 20, genre = '', query = ''): Promise<any> {
        const params = new URLSearchParams({ limit: String(limit), offset: String((page - 1) * limit), sort: 'latest', order: 'desc' });
        if (genre) params.set('genres', genre);
        if (query) params.set('search', query);
        const data = await fetchJSON<any>(`https://api.asurascans.com/api/series?${params}`, BASE);
        if (!Array.isArray(data.data) || !Number.isInteger(data.meta?.total)) throw new Error('Invalid Asura catalogue');
        return {
            results: data.data.map((item: any) => ({
                slug: (item.public_url || `/comics/${item.slug}`).replace(/^\//, ''),
                title: item.title, coverUrl: item.cover || '', status: item.status,
                contentType: item.type || 'unknown',
            })),
            total: data.meta.total,
            has_next: page * limit < data.meta.total,
        };
    }

    async tags(): Promise<any[]> {
        const data = island(await fetchHTML(`${BASE}/browse/comics`, BASE), 'BrowseFilters');
        if (!Array.isArray(data.availableGenres)) throw new Error('Invalid Asura genres');
        return data.availableGenres.map((genre: any) => ({ id: genre.slug, name: genre.name }));
    }

    async search(query: string): Promise<any[]> {
        const data = await fetchJSON<any>(`https://api.asurascans.com/api/search?q=${encodeURIComponent(query)}`, BASE);
        if (!Array.isArray(data.data)) throw new Error('Invalid Asura search response');
        return data.data.map((item: any) => ({
            slug: (item.public_url || `/comics/${item.slug}`).replace(/^\//, ''),
            title: item.title, coverUrl: item.cover || '', status: item.status,
            contentType: item.type || 'unknown', latestChapter: '', rating: 'unknown',
        }));
    }
    async fetchSeriesInfo(slug: string): Promise<any> {
        const html = await fetchHTML(`${BASE}/${seriesPath(slug)}`, BASE);
        const $ = cheerio.load(html);
        const chapters = island(html, 'ChapterListReact');
        const tagLinks = $('a[href*="genres="]').map((_, element) => {
            const name = $(element).text().trim();
            const id = new URL($(element).attr('href') || '', BASE).searchParams.get('genres');
            return id && name ? { id, name } : null;
        }).get();
        return {
            title: $('h1').first().text().trim(), coverUrl: chapters.coverUrl,
            description: $('meta[property="og:description"]').attr('content') || $('meta[name="description"]').attr('content') || '',
            genres: tagLinks.map(tag => tag.name), tagLinks, authors: [], status: 'Não informado', contentType: 'unknown',
        };
    }
    async fetchChapters(slug: string): Promise<any[]> {
        const data = island(await fetchHTML(`${BASE}/${seriesPath(slug)}`, BASE), 'ChapterListReact');
        if (!Array.isArray(data.chapters)) throw new Error('Invalid Asura chapters');
        return data.chapters.filter((c: any) => !c.is_premium &&
            (!c.early_access_until || new Date(c.early_access_until).getTime() <= Date.now()))
            .map((c: any) => ({
                slug: `${(data.publicUrl || '/' + seriesPath(slug)).replace(/^\//, '')}/chapter/${c.number}`,
                number: String(c.number), title: c.title || '', date: c.published_at || '',
            }));
    }
    async fetchChapterPages(slug: string): Promise<string[]> {
        const data = island(await fetchHTML(`${BASE}/${slug}`, BASE), 'ChapterReader');
        if (data.isLocked || data.isPremium) throw new Error('Chapter is not publicly accessible');
        if (!Array.isArray(data.pages)) throw new Error('Invalid Asura pages');
        return data.pages.map((p: any) => p.url).filter((url: any) => typeof url === 'string' && url.startsWith('https://cdn.asurascans.com/'));
    }
}
