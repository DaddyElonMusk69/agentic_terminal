<template>
  <div class="rounded-lg border border-border bg-panel p-3">
    <div class="flex items-center justify-between text-xs text-muted">
      <button
        class="rounded-md border border-border px-2 py-1 text-[10px] hover:text-text"
        type="button"
        @click="changeMonth(-1)"
      >
        Prev
      </button>
      <span class="font-display text-[11px] uppercase tracking-widest text-text">
        {{ monthLabel }}
      </span>
      <button
        class="rounded-md border border-border px-2 py-1 text-[10px] hover:text-text"
        type="button"
        @click="changeMonth(1)"
      >
        Next
      </button>
    </div>
    <div class="mt-3 grid grid-cols-7 gap-1 text-[10px] text-muted">
      <div v-for="day in dayNames" :key="day" class="text-center">
        {{ day }}
      </div>
      <div
        v-for="cell in calendarCells"
        :key="cell.key"
        class="h-8"
      >
        <button
          v-if="cell.dateStr"
          class="flex h-8 w-full items-center justify-center rounded-md text-[10px]"
          :class="cellClass(cell)"
          :style="cellStyle(cell)"
          type="button"
          @click="$emit('select', cell.dateStr)"
        >
          <span>{{ cell.day }}</span>
        </button>
        <div v-else class="h-8"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";

const props = defineProps<{ data: Record<string, number>; selected?: string | null }>();

defineEmits<{
  (event: "select", date: string): void;
}>();

const currentDate = ref(new Date());

const dayNames = ["S", "M", "T", "W", "T", "F", "S"];

const monthLabel = computed(() =>
  currentDate.value.toLocaleString("default", { month: "long", year: "numeric" }),
);

const maxCount = computed(() => {
  const values = Object.values(props.data);
  return values.length ? Math.max(1, ...values) : 1;
});

const calendarCells = computed(() => {
  const year = currentDate.value.getFullYear();
  const month = currentDate.value.getMonth();
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);
  const daysInMonth = lastDay.getDate();
  const startDayOfWeek = firstDay.getDay();
  const cells = [] as Array<{
    key: string;
    dateStr?: string;
    day?: number;
    count?: number;
  }>;

  for (let i = 0; i < startDayOfWeek; i += 1) {
    cells.push({ key: `blank-${i}` });
  }

  for (let d = 1; d <= daysInMonth; d += 1) {
    const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    const count = props.data[dateStr] || 0;
    cells.push({ key: dateStr, dateStr, day: d, count });
  }

  return cells;
});

const changeMonth = (delta: number) => {
  const next = new Date(currentDate.value);
  next.setMonth(next.getMonth() + delta);
  currentDate.value = next;
};

const cellClass = (cell: { dateStr?: string; count?: number }) => {
  const classes = ["border", "border-border", "text-text", "hover:border-accent"];
  if (!cell.dateStr) return "";
  if (props.selected === cell.dateStr) {
    classes.push("ring-1", "ring-accent");
  }
  if (!cell.count) {
    classes.push("bg-surface", "text-muted");
  }
  return classes.join(" ");
};

const cellStyle = (cell: { count?: number }) => {
  if (!cell.count) return undefined;
  const normalized =
    maxCount.value <= 1
      ? 1
      : Math.log10(cell.count + 1) / Math.log10(maxCount.value + 1);
  const intensity = Math.min(1, Math.max(0, normalized));
  const alpha = 0.12 + intensity * 0.6;
  return { backgroundColor: `rgb(var(--color-accent) / ${alpha})` };
};
</script>
