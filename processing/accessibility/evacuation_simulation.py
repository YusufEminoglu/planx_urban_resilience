# -*- coding: utf-8 -*-
"""Evacuation Time Simulation (greedy capacity-constrained assignment).

Macro screening model: origins with population are assigned to shelters
along shortest network paths, respecting shelter capacity. Optional timestep
queueing defers departures when road segments exceed a per-interval flow cap.

Not a dynamic traffic microsimulation — suitable for planning studios.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsWkbTypes,
)

from ._network_graph import (
    build_road_graph,
    dijkstra_predecessors,
    feature_point,
    iter_features,
    nearest_graph_node,
    percentile,
    reconstruct_path_edges,
    segment_length,
    travel_time_minutes,
)


def _evac_class(minutes: float, target: float, critical: float, assigned: bool) -> str:
    if not assigned or minutes < 0:
        return "Unassigned"
    if minutes <= target:
        return "OnTime"
    if minutes <= (target + critical) * 0.5:
        return "Watch"
    if minutes <= critical:
        return "Late"
    return "Late"


def _pop_value(feature, field_name):
    try:
        value = feature[field_name]
        if value in (None, ""):
            return 0.0
        return max(0.0, float(value))
    except (KeyError, TypeError, ValueError):
        return 0.0


def _capacity_value(feature, field_name):
    try:
        value = feature[field_name]
        if value in (None, ""):
            return 0.0
        return max(0.0, float(value))
    except (KeyError, TypeError, ValueError):
        return 0.0


def _path_capacity_ok(path_edges, step_load, pop, cap_per_step):
    for eid in path_edges:
        if step_load[eid] + pop > cap_per_step.get(eid, 0.0):
            return False
    return True


def _add_path_load(path_edges, step_load, pop):
    for eid in path_edges:
        step_load[eid] += pop


@dataclass
class ShelterSlot:
    feature: QgsFeature
    name: str
    node: tuple
    capacity_total: float
    capacity_left: float
    assign_count: int = 0


@dataclass
class OriginJob:
    feature: QgsFeature
    population: float
    node: tuple | None
    snap_ok: bool
    assigned: bool = False
    shelter_name: str = ""
    travel_min: float = -1.0
    evac_min: float = -1.0
    delay_min: float = 0.0
    evac_timestep: int = -1
    evac_class: str = "Unassigned"
    qa_flag: str = "ok"
    path_edges: list[int] = field(default_factory=list)


from .._mixins import GROUP_EMERGENCY, GroupMixin, HelpUrlMixin  # noqa: E402


class EvacuationTimeSimulationAlgorithm(HelpUrlMixin, GroupMixin, QgsProcessingAlgorithm):
    GROUP = GROUP_EMERGENCY
    ICON = "tool_evacuation_time_simulation.png"
    ROADS = "ROADS"
    ORIGINS = "ORIGINS"
    POP_FIELD = "POP_FIELD"
    SHELTERS = "SHELTERS"
    CAPACITY_FIELD = "CAPACITY_FIELD"
    SPEED_KMH = "SPEED_KMH"
    TARGET_MINUTES = "TARGET_MINUTES"
    CRITICAL_MINUTES = "CRITICAL_MINUTES"
    ROAD_CAPACITY_FIELD = "ROAD_CAPACITY_FIELD"
    ROAD_CLASS_FIELD = "ROAD_CLASS_FIELD"
    ROAD_DIRECTION_FIELD = "ROAD_DIRECTION_FIELD"
    DEFAULT_LANE_CAPACITY = "DEFAULT_LANE_CAPACITY"
    TIMESTEP_MINUTES = "TIMESTEP_MINUTES"
    MAX_TIMESTEPS = "MAX_TIMESTEPS"
    SNAP_TOLERANCE = "SNAP_TOLERANCE"
    ASSIGN_ORDER = "ASSIGN_ORDER"
    OUTPUT_ORIGINS = "OUTPUT_ORIGINS"
    OUTPUT_SHELTERS = "OUTPUT_SHELTERS"
    OUTPUT_EDGES = "OUTPUT_EDGES"

    ASSIGN_OPTIONS = ("Farthest first", "Largest population first")

    def tr(self, string):
        return string

    def createInstance(self):
        return EvacuationTimeSimulationAlgorithm()

    def name(self):
        return "evacuation_time_simulation"

    def displayName(self):
        return self.tr("Evacuation Time Simulation")

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Evacuation Time Simulation</h3>
            <p>Greedy capacity-constrained shelter assignment with optional timestep
            queueing, in the macroscopic-flow tradition Daganzo's (1994) Cell
            Transmission Model established: discretise time into steps and cap how much
            flow crosses a link per step, without simulating individual vehicles.
            Yperman's (2007) Link Transmission Model refined that for large networks;
            TIMESTEP_MINUTES here is a simplified, planning-scale instance of the same
            discretised-flow-with-capacity-cap logic. Shelter assignment itself is a
            greedy nearest-capacity heuristic in the Church &amp; ReVelle (1974)
            facility-location tradition.</p>
            <p>Assignment is order-dependent: ASSIGN_ORDER (farthest-first vs
            largest-population-first) changes which shelters fill and which origins go
            unassigned, because greedy locks in early decisions later origins must live
            with. Road capacity is a fixed persons/hour ceiling with no speed-density
            degradation as flow approaches it - real traffic flow slows non-linearly near
            jam density, which this hard cap does not represent. Timestep minutes = 0
            means instant greedy assignment, no queueing.</p>
            <p>How to read the results
            - qa_flag = no_capacity: population that could not be assigned - it does not
            vanish, it needs more shelter capacity or more sites (feed into Optimal
            Shelter Siting).
            - congestion_pct &gt; 100 on an edge: assigned load exceeds its hourly
            capacity - a bottleneck.
            - P95 evacuation time (in the log): the time by which 95% of assigned
            population has reached a shelter; compare instant vs timestep-queue mode to
            see the congestion delay.</p>
            <p>Using the results: feed congested edges into Cost-Benefit Analyzer to rank
            road-widening interventions. This model assumes perfect compliance - no
            shadow evacuation (people leaving who weren't told to) or evacuation refusal,
            both well-documented real behaviours (Murray-Tuite &amp; Wolshon, 2013). Use
            it for macro-scale screening and assignment-order sensitivity, not for
            micro-level traffic-engineering decisions (signal timing, lane geometry) -
            that needs a true microsimulation.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.ROADS, self.tr("Road network (lines)"),
            [QgsProcessing.TypeVectorLine],
        ))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.ORIGINS,
            self.tr("Origins (buildings / population assets)"),
            [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.POP_FIELD, self.tr("Population field"),
            parentLayerParameterName=self.ORIGINS,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.SHELTERS, self.tr("Shelters / safe assembly areas"),
            [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.CAPACITY_FIELD, self.tr("Shelter capacity field"),
            parentLayerParameterName=self.SHELTERS,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.SPEED_KMH, self.tr("Assumed travel speed (km/h)"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=30.0, minValue=0.5, maxValue=120.0,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.TARGET_MINUTES, self.tr("Target evacuation time (minutes)"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=15.0, minValue=1.0, maxValue=240.0,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.CRITICAL_MINUTES, self.tr("Critical evacuation time (minutes)"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=45.0, minValue=1.0, maxValue=480.0,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.ROAD_CAPACITY_FIELD,
            self.tr("Road capacity field (persons/hour, optional)"),
            parentLayerParameterName=self.ROADS,
            type=QgsProcessingParameterField.Numeric,
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.ROAD_CLASS_FIELD,
            self.tr("Road class field (optional, e.g. arterial/collector/local)"),
            parentLayerParameterName=self.ROADS,
            type=QgsProcessingParameterField.String,
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.ROAD_DIRECTION_FIELD,
            self.tr("Road direction field (optional: both / ft / bt)"),
            parentLayerParameterName=self.ROADS,
            type=QgsProcessingParameterField.String,
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.DEFAULT_LANE_CAPACITY,
            self.tr("Default road capacity (persons/hour)"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=1200.0, minValue=1.0,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.TIMESTEP_MINUTES,
            self.tr("Timestep for road queue (minutes, 0 = instant)"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.0, minValue=0.0, maxValue=60.0,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.MAX_TIMESTEPS,
            self.tr("Maximum queue timesteps"),
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=48, minValue=1, maxValue=500,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.SNAP_TOLERANCE, self.tr("Snap tolerance (map units)"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=2.0, minValue=0.01,
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.ASSIGN_ORDER,
            self.tr("Greedy assignment order"),
            options=list(self.ASSIGN_OPTIONS),
            defaultValue=0,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT_ORIGINS, self.tr("Evacuation origins"),
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT_SHELTERS, self.tr("Shelter utilization"),
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT_EDGES, self.tr("Evacuation edge load"),
        ))

    def _assign_one(
        self,
        job: OriginJob,
        node_to_slots,
        route_origin,
        target_min,
        critical_min,
    ) -> bool:
        if not job.snap_ok:
            job.qa_flag = "not_snapped"
            return False
        _distances, predecessor, reachable = route_origin(job)
        for travel_min, node in reachable:
            path_edges = reconstruct_path_edges(predecessor, job.node, node)
            if not path_edges:
                continue
            for slot in sorted(node_to_slots[node], key=lambda s: s.name):
                if slot.capacity_left < job.population:
                    continue
                slot.capacity_left -= job.population
                slot.assign_count += 1
                job.assigned = True
                job.shelter_name = slot.name
                job.travel_min = travel_min
                job.evac_min = travel_min
                job.delay_min = 0.0
                job.evac_timestep = 0
                job.evac_class = _evac_class(travel_min, target_min, critical_min, True)
                job.path_edges = path_edges
                job.qa_flag = "ok"
                return True
        job.qa_flag = "no_capacity"
        return False

    def _run_instant(
        self,
        jobs,
        node_to_slots,
        route_origin,
        target_min,
        critical_min,
    ):
        for job in jobs:
            if job.assigned:
                continue
            self._assign_one(job, node_to_slots, route_origin, target_min, critical_min)

    def _run_timestep_queue(
        self,
        jobs,
        node_to_slots,
        route_origin,
        target_min,
        critical_min,
        edge_capacity,
        timestep_min,
        max_timesteps,
        feedback,
    ):
        cap_per_step = {
            eid: cap * (timestep_min / 60.0)
            for eid, cap in edge_capacity.items()
        }
        pending = [j for j in jobs if j.snap_ok and not j.assigned]
        for t in range(max_timesteps):
            if feedback.isCanceled():
                break
            step_load: dict[int, float] = defaultdict(float)
            progress = False
            for job in pending[:]:
                if job.assigned:
                    continue
                _distances, predecessor, reachable = route_origin(job)
                placed = False
                for travel_min, node in reachable:
                    path_edges = reconstruct_path_edges(predecessor, job.node, node)
                    if not path_edges:
                        continue
                    if not _path_capacity_ok(path_edges, step_load, job.population, cap_per_step):
                        continue
                    for slot in sorted(node_to_slots[node], key=lambda s: s.name):
                        if slot.capacity_left < job.population:
                            continue
                        _add_path_load(path_edges, step_load, job.population)
                        slot.capacity_left -= job.population
                        slot.assign_count += 1
                        delay = t * timestep_min
                        total = delay + travel_min
                        job.assigned = True
                        job.shelter_name = slot.name
                        job.travel_min = travel_min
                        job.delay_min = delay
                        job.evac_min = total
                        job.evac_timestep = t
                        job.evac_class = _evac_class(total, target_min, critical_min, True)
                        job.path_edges = path_edges
                        job.qa_flag = "ok"
                        placed = True
                        progress = True
                        break
                    if placed:
                        break
            pending = [j for j in pending if not j.assigned]
            if not pending:
                break
            if not progress:
                feedback.pushInfo(
                    f"Queue stalled at timestep {t}; {len(pending)} origins remain unassigned."
                )
                break

        for job in jobs:
            if not job.snap_ok:
                job.qa_flag = "not_snapped"
            elif not job.assigned:
                job.qa_flag = "no_capacity"

    def processAlgorithm(self, parameters, context, feedback):
        roads = self.parameterAsSource(parameters, self.ROADS, context)
        origins = self.parameterAsSource(parameters, self.ORIGINS, context)
        shelters = self.parameterAsSource(parameters, self.SHELTERS, context)
        if roads is None or origins is None or shelters is None:
            raise QgsProcessingException("Roads, origins and shelters are all required.")

        pop_field = self.parameterAsString(parameters, self.POP_FIELD, context)
        cap_field = self.parameterAsString(parameters, self.CAPACITY_FIELD, context)
        speed_kmh = self.parameterAsDouble(parameters, self.SPEED_KMH, context)
        target_min = self.parameterAsDouble(parameters, self.TARGET_MINUTES, context)
        critical_min = max(
            self.parameterAsDouble(parameters, self.CRITICAL_MINUTES, context),
            target_min,
        )
        road_cap_field = self.parameterAsString(parameters, self.ROAD_CAPACITY_FIELD, context) or ""
        road_class_field = self.parameterAsString(parameters, self.ROAD_CLASS_FIELD, context) or ""
        road_direction_field = self.parameterAsString(parameters, self.ROAD_DIRECTION_FIELD, context) or ""
        default_lane_cap = self.parameterAsDouble(parameters, self.DEFAULT_LANE_CAPACITY, context)
        timestep_min = self.parameterAsDouble(parameters, self.TIMESTEP_MINUTES, context)
        max_timesteps = int(self.parameterAsInt(parameters, self.MAX_TIMESTEPS, context))
        tolerance = self.parameterAsDouble(parameters, self.SNAP_TOLERANCE, context)
        assign_order = self.parameterAsEnum(parameters, self.ASSIGN_ORDER, context)

        feedback.pushInfo("Building road graph...")
        graph, nodes, edges, edge_capacity = build_road_graph(
            roads,
            tolerance,
            capacity_field=road_cap_field or None,
            class_field=road_class_field or None,
            direction_field=road_direction_field or None,
            default_capacity=default_lane_cap,
        )
        if not edges:
            raise QgsProcessingException(
                "Empty road network after snapping; check geometry or snap tolerance."
            )

        shelter_slots: list[ShelterSlot] = []
        node_to_slots: dict[tuple, list[ShelterSlot]] = defaultdict(list)
        for feat in iter_features(shelters):
            node = nearest_graph_node(feature_point(feat.geometry()), nodes, tolerance)
            if node is None:
                continue
            name = str(feat.id())
            for fld in shelters.fields():
                if fld.name().lower() in ("name", "label", "shelter"):
                    val = feat[fld.name()]
                    if val not in (None, ""):
                        name = str(val)
                        break
            cap = _capacity_value(feat, cap_field)
            slot = ShelterSlot(
                feature=feat,
                name=name,
                node=node,
                capacity_total=cap,
                capacity_left=cap,
            )
            shelter_slots.append(slot)
            node_to_slots[node].append(slot)

        if not shelter_slots:
            raise QgsProcessingException("No shelter snapped to the road network.")

        dest_nodes = set(node_to_slots.keys())

        jobs: list[OriginJob] = []
        for feat in iter_features(origins):
            pop = _pop_value(feat, pop_field)
            if pop <= 0:
                continue
            node = nearest_graph_node(feature_point(feat.geometry()), nodes, tolerance)
            jobs.append(OriginJob(
                feature=feat,
                population=pop,
                node=node,
                snap_ok=node is not None,
            ))

        if not jobs:
            raise QgsProcessingException("No origins with positive population snapped to the network.")

        routing_cache: dict[tuple, tuple] = {}

        def route_origin(job: OriginJob):
            if job.node is None:
                return {}, {}, []
            if job.node in routing_cache:
                return routing_cache[job.node]
            distances, predecessor = dijkstra_predecessors(graph, job.node, dest_nodes)
            reachable = [
                (travel_time_minutes(distances[n], speed_kmh), n)
                for n in dest_nodes if n in distances
            ]
            reachable.sort(key=lambda item: item[0])
            routing_cache[job.node] = (distances, predecessor, reachable)
            return routing_cache[job.node]

        def sort_key(job: OriginJob):
            if job.node is None:
                return float("inf") if assign_order == 0 else 0.0
            _distances, _pred, reachable = route_origin(job)
            if not reachable:
                return float("inf") if assign_order == 0 else 0.0
            if assign_order == 0:
                return -reachable[0][0]
            return -job.population

        jobs.sort(key=sort_key)

        if timestep_min > 0:
            feedback.pushInfo(
                f"Timestep queue: {timestep_min} min intervals, max {max_timesteps} steps."
            )
            self._run_timestep_queue(
                jobs, node_to_slots, route_origin, target_min, critical_min,
                edge_capacity, timestep_min, max_timesteps, feedback,
            )
        else:
            self._run_instant(jobs, node_to_slots, route_origin, target_min, critical_min)
            for job in jobs:
                if not job.snap_ok:
                    job.qa_flag = "not_snapped"
                elif not job.assigned:
                    job.qa_flag = "no_capacity"

        trip_count: dict[int, int] = defaultdict(int)
        pop_load: dict[int, float] = defaultdict(float)
        assigned_times: list[float] = []
        assigned_pop = 0.0
        unassigned_pop = 0.0

        origin_fields = QgsFields()
        for fld in origins.fields():
            origin_fields.append(fld)
        for fname, ftype in (
            ("evac_shelter", QVariant.String),
            ("travel_min", QVariant.Double),
            ("evac_delay_min", QVariant.Double),
            ("evac_min", QVariant.Double),
            ("evac_timestep", QVariant.Int),
            ("evac_pop", QVariant.Double),
            ("evac_class", QVariant.String),
            ("qa_flag", QVariant.String),
        ):
            if origin_fields.indexOf(fname) < 0:
                origin_fields.append(QgsField(fname, ftype))

        (origin_sink, origin_id) = self.parameterAsSink(
            parameters, self.OUTPUT_ORIGINS, context, origin_fields,
            origins.wkbType(), origins.sourceCrs(),
        )

        extra = 8
        for idx, job in enumerate(jobs):
            if job.assigned:
                assigned_pop += job.population
                assigned_times.append(job.evac_min)
                for eid in job.path_edges:
                    trip_count[eid] += 1
                    pop_load[eid] += job.population
            else:
                unassigned_pop += job.population

            out = QgsFeature(origin_fields)
            out.setGeometry(job.feature.geometry())
            attrs = list(job.feature.attributes())
            while len(attrs) < origin_fields.size() - extra:
                attrs.append(None)
            attrs.extend([
                job.shelter_name,
                job.travel_min if job.assigned else -1.0,
                job.delay_min if job.assigned else 0.0,
                job.evac_min,
                job.evac_timestep,
                job.population,
                job.evac_class,
                job.qa_flag,
            ])
            out.setAttributes(attrs)
            origin_sink.addFeature(out, QgsFeatureSink.FastInsert)
            feedback.setProgress(int((idx + 1) / max(len(jobs), 1) * 100))

        shelter_fields = QgsFields()
        for fld in shelters.fields():
            shelter_fields.append(fld)
        for fname, ftype in (
            ("cap_total", QVariant.Double),
            ("cap_used", QVariant.Double),
            ("cap_pct", QVariant.Double),
            ("assign_count", QVariant.Int),
        ):
            if shelter_fields.indexOf(fname) < 0:
                shelter_fields.append(QgsField(fname, ftype))

        (shelter_sink, shelter_id) = self.parameterAsSink(
            parameters, self.OUTPUT_SHELTERS, context, shelter_fields,
            shelters.wkbType(), shelters.sourceCrs(),
        )
        for slot in shelter_slots:
            used = slot.capacity_total - slot.capacity_left
            pct = (100.0 * used / slot.capacity_total) if slot.capacity_total > 0 else 0.0
            out = QgsFeature(shelter_fields)
            out.setGeometry(slot.feature.geometry())
            attrs = list(slot.feature.attributes())
            while len(attrs) < shelter_fields.size() - 4:
                attrs.append(None)
            attrs.extend([slot.capacity_total, used, pct, slot.assign_count])
            out.setAttributes(attrs)
            shelter_sink.addFeature(out, QgsFeatureSink.FastInsert)

        edge_fields = QgsFields()
        edge_fields.append(QgsField("edge_id", QVariant.Int))
        edge_fields.append(QgsField("length_m", QVariant.Double))
        edge_fields.append(QgsField("trip_count", QVariant.Int))
        edge_fields.append(QgsField("load_pop", QVariant.Double))
        edge_fields.append(QgsField("road_capacity_ph", QVariant.Double))
        edge_fields.append(QgsField("congestion_pct", QVariant.Double))
        edge_fields.append(QgsField("bottleneck_score", QVariant.Double))

        (edge_sink, edge_id) = self.parameterAsSink(
            parameters, self.OUTPUT_EDGES, context, edge_fields,
            QgsWkbTypes.LineString, roads.sourceCrs(),
        )

        max_trips = max(trip_count.values()) if trip_count else 1
        for eid, (n1, n2) in edges.items():
            trips = trip_count.get(eid, 0)
            load = pop_load.get(eid, 0.0)
            cap_ph = edge_capacity.get(eid, default_lane_cap)
            congestion = min(100.0, 100.0 * load / cap_ph) if cap_ph > 0 else 0.0
            score = (100.0 * trips / max_trips) if max_trips > 0 else 0.0
            length = segment_length(n1, n2)
            line_geom = QgsGeometry.fromPolylineXY(
                [QgsPointXY(n1[0], n1[1]), QgsPointXY(n2[0], n2[1])]
            )
            feat = QgsFeature(edge_fields)
            feat.setGeometry(line_geom)
            feat.setAttributes([eid, length, trips, load, cap_ph, congestion, score])
            edge_sink.addFeature(feat, QgsFeatureSink.FastInsert)

        assigned_times.sort()
        p50 = percentile(assigned_times, 50) if assigned_times else 0.0
        p95 = percentile(assigned_times, 95) if assigned_times else 0.0
        feedback.pushInfo(
            f"Assigned population: {assigned_pop:.0f} | Unassigned: {unassigned_pop:.0f}"
        )
        feedback.pushInfo(
            f"Evacuation time P50: {p50:.1f} min | P95: {p95:.1f} min "
            f"(n={len(assigned_times)} origins)"
        )
        congested = sum(1 for eid in edges if pop_load.get(eid, 0) > edge_capacity.get(eid, default_lane_cap))
        if congested:
            feedback.pushInfo(
                f"Edges with assigned load above hourly capacity: {congested} (screening flag)."
            )

        return {
            self.OUTPUT_ORIGINS: origin_id,
            self.OUTPUT_SHELTERS: shelter_id,
            self.OUTPUT_EDGES: edge_id,
        }
