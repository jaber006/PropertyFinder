const axios = require('axios');

async function test() {
  // Domain's internal search API (used by the frontend)
  const url = 'https://www.domain.com.au/phoenix/api/listings?listingType=sale&propertyTypes=house,townhouse,duplex,semiDetached&minBedrooms=3&minBathrooms=2&minPrice=1800000&maxPrice=2800000&locations=arncliffe-nsw-2205,rockdale-nsw-2216,bexley-nsw-2207,banksia-nsw-2216,wolli-creek-nsw-2205&page=1&pageSize=100';
  
  console.log('Trying Domain internal API...');
  try {
    const r = await axios.get(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json'
      },
      timeout: 30000
    });
    console.log('Status:', r.status);
    console.log('Type:', typeof r.data);
    if (typeof r.data === 'object') {
      console.log('Keys:', Object.keys(r.data));
      console.log(JSON.stringify(r.data).slice(0, 1000));
    } else {
      console.log('First 500 chars:', String(r.data).slice(0, 500));
    }
  } catch(e) {
    console.log('Phoenix API failed:', e.response?.status || e.code, e.message);
  }

  // Try Domain's GraphQL endpoint
  console.log('\nTrying Domain GraphQL...');
  try {
    const r2 = await axios.post('https://www.domain.com.au/graphql', {
      operationName: 'searchByQuery',
      variables: {
        query: 'arncliffe',
        pageSize: 20,
        page: 1,
        listingType: 'sale'
      }
    }, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Content-Type': 'application/json'
      },
      timeout: 15000
    });
    console.log('GraphQL Status:', r2.status);
    console.log(JSON.stringify(r2.data).slice(0, 500));
  } catch(e) {
    console.log('GraphQL failed:', e.response?.status || e.code);
  }

  // Try lighter web_fetch equivalent: just the first suburb
  console.log('\nSingle suburb fetch (Arncliffe only)...');
  console.time('single');
  try {
    const r3 = await axios.get('https://www.domain.com.au/sale/arncliffe-nsw-2205/?bedrooms=3-any&price=1800000-2800000&ptype=house', {
      headers: { 
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept-Encoding': 'gzip, deflate, br'
      },
      timeout: 60000,
      decompress: true
    });
    console.timeEnd('single');
    console.log('Size:', (r3.data.length / 1024).toFixed(0) + 'KB');
  } catch(e) {
    console.timeEnd('single');
    console.log('Single failed:', e.code || e.response?.status);
  }
}

test().catch(e => console.error(e.message));
