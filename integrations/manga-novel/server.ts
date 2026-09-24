// Local entry point: mount the upstream multi-provider router, which the
// upstream server.ts currently leaves unused. Original source stays intact.
import express from 'express';
import helmet from 'helmet';
import { mangaRouter } from './routes/manga';
import { proxyRouter } from './proxy/imageProxy';
import { AsuraScraper } from './scrapers/asuraScraper';
import { ComickScraper } from './scrapers/comickScraper';
import { WeebCentralScraper } from './scrapers/weebCentralScraper';
const app = express();
app.use(helmet());
app.get('/api/health', (_req, res) => res.json({ status: 'ok' }));
app.get('/api/manga/catalog', async (req, res, next) => {
    try {
        const source = String(req.query.source || '');
        const page = Math.max(1, Math.min(500, Number(req.query.page) || 1));
        const limit = 20;
        if (source === 'asura') {
            const result = await new AsuraScraper().browse(page, limit, String(req.query.tag || ''), String(req.query.q || ''));
            res.json({ source, ...result });
            return;
        }
        if (req.query.tag) { res.status(400).json({ error: 'Genre filtering is unsupported for this source' }); return; }
        let results;
        if (source === 'comick') results = await new ComickScraper().trending(undefined, page);
        else if (source === 'weebcentral') results = await new WeebCentralScraper().search('', page);
        else { res.status(400).json({ error: 'Unknown catalog source' }); return; }
        res.json({ source, results, total: null, has_next: results.length >= limit });
    } catch (error) { next(error); }
});
app.get('/api/manga/tags', async (req, res, next) => {
    if (req.query.source !== 'asura') { res.status(400).json({ error: 'Unsupported source' }); return; }
    try { res.json({ source: 'asura', tags: await new AsuraScraper().tags() }); }
    catch (error) { next(error); }
});
app.use('/api/manga', mangaRouter);
app.use('/api/proxy', proxyRouter);
app.use((_req, res) => res.status(404).json({ error: 'Not found' }));
app.use((error: Error, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
    console.error(error.message);
    res.status(502).json({ error: 'Source temporarily unavailable' });
});
app.listen(3001, '0.0.0.0');
