const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('./dist/src/utils/httpClient');
const { AsuraScraper, decode } = require('./dist/src/scrapers/asuraScraper');
function encode(value) {
  if (Array.isArray(value)) return [1, value.map(encode)];
  if (value && typeof value === 'object') return [0, Object.fromEntries(Object.entries(value).map(([k,v])=>[k,encode(v)]))];
  return [0,value];
}
function html(component, props) {
  const serialized=JSON.stringify(Object.fromEntries(Object.entries(props).map(([k,v])=>[k,encode(v)]))).replaceAll('"','&quot;');
  return `<astro-island component-url="${component}.js" props="${serialized}"></astro-island>`;
}
test('search uses the actual query endpoint and public source URLs', async()=>{
  http.fetchJSON=async url=>{
    assert.equal(new URL(url).searchParams.get('q'),'solo leveling');
    assert.equal(new URL(url).pathname,'/api/search');
    return {data:[{slug:'solo',public_url:'/comics/solo-hash',title:'Solo',cover:'https://cdn.asurascans.com/cover.webp'}]};
  };
  const result=await new AsuraScraper().search('solo leveling');
  assert.equal(result[0].slug,'comics/solo-hash');
  assert.equal(result[0].coverUrl,'https://cdn.asurascans.com/cover.webp');
});
test('chapter zero survives and unavailable chapters are excluded', async()=>{
  http.fetchHTML=async()=>html('ChapterListReact',{publicUrl:'/comics/solo',chapters:[
    {number:0,is_premium:false},{number:1,is_premium:true},
    {number:2,is_premium:false,early_access_until:'2999-01-01T00:00:00Z'}]});
  const result=await new AsuraScraper().fetchChapters('comics/solo');
  assert.deepEqual(result.map(c=>c.number),['0']);
  assert.equal(result[0].slug,'comics/solo/chapter/0');
});
test('reader accepts only public pages and refuses locked chapters', async()=>{
  http.fetchHTML=async()=>html('ChapterReader',{isLocked:false,isPremium:false,pages:[{url:'https://cdn.asurascans.com/a.webp'},{url:'https://unrelated.example/a'}]});
  assert.deepEqual(await new AsuraScraper().fetchChapterPages('comics/solo/chapter/0'),['https://cdn.asurascans.com/a.webp']);
  http.fetchHTML=async()=>html('ChapterReader',{isLocked:true,pages:[]});
  await assert.rejects(()=>new AsuraScraper().fetchChapterPages('comics/solo/chapter/1'));
});
test('catalog requests the correct offset and retains the actual total', async()=>{
  http.fetchJSON=async url=>{
    const parsed=new URL(url);
    assert.equal(parsed.pathname,'/api/series');
    assert.equal(parsed.searchParams.get('offset'),'20');
    assert.equal(parsed.searchParams.get('limit'),'20');
    return {data:[{slug:'second-page',public_url:'/comics/second-page-hash',title:'Second page',cover:'https://cdn.asurascans.com/a.webp'}],meta:{total:41}};
  };
  const result=await new AsuraScraper().browse(2);
  assert.equal(result.total,41);
  assert.equal(result.has_next,true);
  assert.equal(result.results[0].slug,'comics/second-page-hash');
});
test('genre catalogue sends the genre and optional title to the upstream API', async()=>{
  http.fetchJSON=async url=>{
    const params=new URL(url).searchParams;
    assert.equal(params.get('genres'),'isekai');
    assert.equal(params.get('search'),'world');
    assert.equal(params.get('offset'),'20');
    return {data:[],meta:{total:20}};
  };
  const result=await new AsuraScraper().browse(2,20,'isekai','world');
  assert.equal(result.has_next,false);
});
test('genre names and IDs are read from real public page fields', async()=>{
  http.fetchHTML=async()=>html('BrowseFilters',{availableGenres:[{id:24,name:'Isekai',slug:'isekai'}]});
  assert.deepEqual(await new AsuraScraper().tags(),[{id:'isekai',name:'Isekai'}]);
  http.fetchHTML=async()=>'<h1>Story</h1><a href="/browse?genres=isekai"> Isekai </a>'+html('ChapterListReact',{coverUrl:'cover'});
  const info=await new AsuraScraper().fetchSeriesInfo('comics/story');
  assert.deepEqual(info.tagLinks,[{id:'isekai',name:'Isekai'}]);
  assert.deepEqual(info.genres,['Isekai']);
});
