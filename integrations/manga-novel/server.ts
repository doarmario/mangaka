// Local entry point: mount the upstream multi-provider router, which the
// upstream server.ts currently leaves unused. Original source stays intact.
import express from 'express';
import helmet from 'helmet';
import { mangaRouter } from './routes/manga';
import { proxyRouter } from './proxy/imageProxy';
const app = express();
app.use(helmet());
app.get('/api/health', (_req, res) => res.json({ status: 'ok' }));
app.use('/api/manga', mangaRouter);
app.use('/api/proxy', proxyRouter);
app.use((_req, res) => res.status(404).json({ error: 'Not found' }));
app.use((error: Error, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
    console.error(error.message);
    res.status(502).json({ error: 'Source temporarily unavailable' });
});
app.listen(3001, '0.0.0.0');
