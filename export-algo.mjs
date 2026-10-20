import fs from 'node:fs/promises';
import {Workbook} from 'file:///C:/Users/kavis/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
const raw = [
['2026-10-06',-3.28,'Signal 1Capital Allocated :80.00% -10,491.00 BNIFTY26O0622900CENSEEntry:7.40Exit:3.05Qty:260SNIFTY26O0622500CENSEEntry:119.50Exit:155.50Qty:26010:24Oct 5, 26-09:47Oct 6, 261 Targets Hit -View'],
['2026-09-01',14.20,'Signal 1Capital Allocated :100.00% 45,451.25 BNIFTY2690124550CENSEEntry:18.30Exit:0.35Qty:325SNIFTY2690124150CENSEEntry:160.60Exit:2.80Qty:32512:40Aug 27, 26-14:57Sep 1, 261 Targets Hit -View'],
['2026-09-08',6.50,'Signal 1Capital Allocated :80.00% 20,787.00 SNIFTY2690823800CENSEEntry:89.45Exit:4.65Qty:260BNIFTY2690824200CENSEEntry:5.15Exit:0.30Qty:26010:49Sep 7, 26-14:57Sep 8, 261 Targets Hit -View'],
['2026-09-29',11.20,'Signal 1Capital Allocated :100.00% 35,831.25 BNIFTY26SEP23550CENSEEntry:10.30Exit:0.25Qty:325SNIFTY26SEP23150CENSEEntry:120.65Exit:0.35Qty:32514:09Sep 25, 26-14:57Sep 29, 261 Targets Hit -View'],
['2026-08-11',7.19,'Signal 1Capital Allocated :80.00% 23,023.00 BNIFTY2681125000CENSEEntry:4.50Exit:0.10Qty:260SNIFTY2681124600CENSEEntry:97.35Exit:4.40Qty:26011:36Aug 10, 26-14:57Aug 11, 261 Targets Hit -View'],
['2026-08-18',13.52,'Signal 1Capital Allocated :100.00% 43,257.50 BNIFTY2681824750CENSEEntry:13.10Exit:0.10Qty:325SNIFTY2681824350CENSEEntry:147.65Exit:1.55Qty:32513:15Aug 13, 26-14:57Aug 18, 261 Targets Hit -View'],
['2026-08-25',9.91,'Signal 1Capital Allocated :100.00% 31,703.75 SNIFTY26AUG24250CENSEEntry:137.90Exit:32.45Qty:325BNIFTY26AUG24650CENSEEntry:8.05Exit:0.15Qty:32513:17Aug 20, 26-14:57Aug 25, 261 Targets Hit -View'],
['2026-07-13',3.24,'Signal 1Capital Allocated :80.00% 10,361.00 BNIFTY2671423700PENSEEntry:9.80Exit:8.80Qty:260SNIFTY2671424100PENSEEntry:89.25Exit:48.40Qty:26010:27Jul 13, 26-12:52Jul 13, 261 Targets Hit -View'],
['2026-07-21',4.77,'Signal 1Capital Allocated :100.00% 15,258.75 BNIFTY2672123850PENSEEntry:29.75Exit:0.20Qty:325SNIFTY2672124250PENSEEntry:146.10Exit:69.60Qty:32510:52Jul 17, 26-14:57Jul 21, 261 Targets Hit -View'],
['2026-05-04',4.78,'Signal 1Capital Allocated :80.00% 15,288.00 BNIFTY2650524600CENSEEntry:19.35Exit:9.55Qty:260SNIFTY2650524200CENSEEntry:134.25Exit:65.65Qty:26010:34May 4, 26-13:29May 4, 261 Targets Hit -View'],
['2026-05-18',4.83,'Signal 1Capital Allocated :80.00% 15,470.00 SNIFTY2651923500PENSEEntry:142.80Exit:73.60Qty:260BNIFTY2651923100PENSEEntry:24.65Exit:14.95Qty:26012:05May 18, 26-13:03May 18, 261 Targets Hit -View'],
['2026-03-09',-4.20,'Signal 1Capital Allocated :80.00% -13,442.00 BNIFTY2631024200CENSEEntry:69.00Exit:107.80Qty:260SNIFTY2631023800CENSEEntry:243.30Exit:333.80Qty:26010:52Mar 9, 26-14:46Mar 9, 261 Targets Hit -View'],
['2025-12-08',4.02,'Signal 1Capital Allocated :100.00% 12,871.18 BNIFTY09DEC2526400CENSEEntry:4.24Avg Exit:3.32Qty:300SNIFTY09DEC2526100CENSEEntry:80.93Avg Exit:36.41Qty:30010:56Dec 8, 25-13:20Dec 8, 252 Targets Hit -View'],
['2025-12-09',8.61,'Signal 1Capital Allocated :100.00% 27,554.59 SNIFTY09DEC2525950CENSEEntry:101.23Avg Exit:0.40Qty:300BNIFTY09DEC2526250CENSEEntry:8.48Avg Exit:0.20Qty:30013:23Dec 8, 25-14:59Dec 9, 252 Targets Hit -View'],
['2025-12-23',4.27,'Signal 1Capital Allocated :100.00% 13,654.57 SNIFTY23DEC2526150PENSEEntry:51.28Avg Exit:0.86Qty:300BNIFTY23DEC2525850PENSEEntry:4.49Avg Exit:0.25Qty:30014:38Dec 22, 25-14:59Dec 23, 252 Targets Hit -View'],
['2025-11-04',6.64,'Signal 1Capital Allocated :100.00% 21,253.41 SNIFTY04NOV2525750CENSEEntry:83.46Avg Exit:0.71Qty:300BNIFTY04NOV2526050CENSEEntry:11.67Avg Exit:0.45Qty:30012:48Nov 3, 25-14:59Nov 4, 252 Targets Hit -View'],
['2025-11-18',7.71,'Signal 1Capital Allocated :100.00% 24,661.10 SNIFTY18NOV2525950CENSEEntry:96.13Avg Exit:5.35Qty:300BNIFTY18NOV2526250CENSEEntry:8.08Avg Exit:0.20Qty:30010:16Nov 17, 25-14:59Nov 18, 252 Targets Hit -View'],
['2025-10-23',6.29,'Signal 1Capital Allocated :100.00% 20,125.12 BNIFTY28OCT2526350CENSEEntry:43.53Avg Exit:14.55Qty:300SNIFTY28OCT2526050CENSEEntry:180.18Avg Exit:83.33Qty:30011:55Oct 23, 25-15:03Oct 23, 252 Targets Hit -View'],
['2025-10-28',10.58,'Signal 1Capital Allocated :100.00% 33,840.56 SNIFTY28OCT2525950CENSEEntry:130.09Avg Exit:0.76Qty:300BNIFTY28OCT2526250CENSEEntry:16.16Avg Exit:0.35Qty:30011:35Oct 27, 25-14:59Oct 28, 252 Targets Hit -View']
];
const source='https://algos.dhan.co/managers/stratzy/ratio-fluxer-credit-spread-expiry/698075eaf867bf12b20442e5?tab=past-trades';
const months={Jan:'01',Feb:'02',Mar:'03',Apr:'04',May:'05',Jun:'06',Jul:'07',Aug:'08',Sep:'09',Oct:'10',Nov:'11',Dec:'12'};
const dt=(time,mon,day,year)=>`20${year}-${months[mon]}-${day.padStart(2,'0')} ${time}`;
const headers=['close_date','signal','entry_datetime','exit_datetime','capital_allocated_pct','pnl_inr','return_pct','leg1_side','leg1_symbol','leg1_exchange','leg1_entry_price','leg1_exit_price','leg1_exit_price_type','leg1_qty','leg2_side','leg2_symbol','leg2_exchange','leg2_entry_price','leg2_exit_price','leg2_exit_price_type','leg2_qty','targets_hit','result_type','source_url'];
const rows=raw.sort((a,b)=>a[0].localeCompare(b[0])).map(([date,pct,text])=>{
const head=text.match(/^Signal (\d+)Capital Allocated :([\d.]+)%\s+(-?[\d,.]+)/);
const re=/([BS])(NIFTY[A-Z0-9]+?)NSEEntry:([\d.]+)(Avg Exit|Exit):([\d.]+)Qty:(\d{3})/g;
const legs=[...text.matchAll(re)]; if(legs.length!==2)throw Error('Leg parse '+date);
const tail=text.slice(legs[1].index+legs[1][0].length).match(/^(\d{2}:\d{2})([A-Z][a-z]{2}) (\d+), (\d{2})-(\d{2}:\d{2})([A-Z][a-z]{2}) (\d+), (\d{2})(\d+) Targets Hit/);
if(!tail)throw Error('Datetime parse '+date);
const legcols=legs.flatMap(l=>[l[1]==='B'?'BUY':'SELL',l[2],'NSE',+l[3],+l[5],l[4]==='Avg Exit'?'average':'exit',+l[6]]);
return [date,+head[1],dt(...tail.slice(1,5)),dt(...tail.slice(5,9)),+head[2],+head[3].replaceAll(',',''),pct,...legcols,+tail[9],'backtest',source];
});
const expected={'2025-10':53965.68,'2025-11':45914.51,'2025-12':54080.34,'2026-03':-13442,'2026-05':30758,'2026-07':25619.75,'2026-08':97984.25,'2026-09':102069.50,'2026-10':-10491};
if(rows.length!==19||new Set(rows.map(r=>r[0])).size!==19)throw Error('Count');
for(const [m,total] of Object.entries(expected)){const actual=rows.filter(r=>r[0].startsWith(m)).reduce((a,r)=>a+r[5],0);if(Math.abs(total-actual)>.011)throw Error('Monthly reconciliation '+m);}
const wb=Workbook.create();const sheet=wb.worksheets.add('Past trades');sheet.getRange('A1:X20').values=[headers,...rows];wb.recalculate();
console.log((await wb.inspect({kind:'table',range:'Past trades!A1:G4',tableMaxRows:4,tableMaxCols:7})).ndjson);
const escape=v=>{const s=String(v??'');return /[",\r\n]/.test(s)?'"'+s.replaceAll('"','""')+'"':s;};
const csv=sheet.getRange('A1:X20').values.map(r=>r.map(escape).join(',')).join('\r\n')+'\r\n';
await fs.writeFile('ratio-fluxer-past-trades.csv','\uFEFF'+csv,'utf8');
console.log(JSON.stringify({signals:rows.length,legs:rows.length*2,first:rows[0][0],last:rows.at(-1)[0],monthlyChecks:Object.keys(expected).length}));
