export type Candidate={event_id:string;start_utc:string;end_utc:string;observed_span_hours:number;observed_dates:number;detection_count:number;selected_month_detections:number;peak_detection_frp_mw:number|null;singleton:boolean;multi_date_support:boolean;touches_region_grid_edge:boolean;touches_archive_time_edge:boolean;end_in_latest_archive_month:boolean;long_chain_caution:boolean;possible_persistent_source:boolean;marker_lat:number;marker_lon:number};
export type EventResult={candidates:Candidate[];total:number;shown:number;hidden_singletons:number;satellite:string;month:string;filters:string;scope:string;validation:{case_name:string;material_fragments:number;dominant_reference_share:number}[];archive_first_utc:string|null;archive_last_utc:string|null};
export type EventDetail={candidate:Omit<Candidate,'selected_month_detections'|'marker_lat'|'marker_lon'>&{min_lon:number;max_lon:number;min_lat:number;max_lat:number;calendar_span_days:number;max_detection_gap_hours:number;sampled_grid_area_km2:number};daily:{date:string;detections:number;peak_detection_frp_mw:number|null}[];footprint_hexes:string[];footprint_day:string;footprint_count:number;reference_links:{case_id:string;case_name:string;reference_points:number;material_reference_association:boolean;dominant_for_reference:boolean;reference_fragmentation_caution:boolean;shared_candidate_review:boolean;dominant_reference_share:number}[];cautions:string[]};
export type EventLayer={loading?:boolean;error?:string;candidates:Candidate[];selectedId:string|null;detail:EventDetail|null;onSelect:(id:string)=>void};
export function eventWarnings(candidate:Pick<Candidate,'singleton'|'multi_date_support'|'touches_region_grid_edge'|'touches_archive_time_edge'|'end_in_latest_archive_month'|'long_chain_caution'|'possible_persistent_source'>){
 const warnings:string[]=[];
 if(candidate.singleton)warnings.push('Single detection: weak candidate support.');
 else if(!candidate.multi_date_support)warnings.push('Observed on one UTC date only.');
 if(candidate.touches_region_grid_edge)warnings.push('Touches the regional grid edge; the event may continue outside this archive.');
 if(candidate.touches_archive_time_edge||candidate.end_in_latest_archive_month)warnings.push('Near the archive time edge; the observed history may be incomplete.');
 if(candidate.long_chain_caution)warnings.push('Links extend beyond 30 days; chaining may combine separate burning episodes.');
 if(candidate.possible_persistent_source)warnings.push('Long-lived, compact heat source: possible persistent-source contamination.');
 return warnings;
}
export function observedSpan(hours:number){if(hours===0)return '0 h';if(hours<1)return `${Math.round(hours*60)} min`;return hours<48?`${hours.toFixed(1)} h`:`${(hours/24).toFixed(1)} days`;}
export function timelineX(date:string,first:string,last:string,width=640){const start=Date.parse(first+'T00:00:00Z'),end=Date.parse(last+'T00:00:00Z');return 20+(end===start?.5:(Date.parse(date+'T00:00:00Z')-start)/(end-start))*(width-40);}
